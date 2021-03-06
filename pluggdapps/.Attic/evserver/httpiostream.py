# -*- coding: utf-8 -*-

# Derived work from Facebook's tornado server.

"""A utility class to write to and read from a non-blocking socket."""

import sys, os, re, collections, errno, socket, ssl

import pluggdapps.utils as h
import pluggdapps.utils.stack_context as sc

class HTTPIOStream( object ):
    r"""A utility class to write to and read from a non-blocking socket.

    We support a non-blocking ``write()`` and a family of ``read_*()`` methods.
    All of the methods take callbacks (since writing and reading are
    non-blocking and asynchronous).

    The socket is a resulting connected socket via socket.accept()."""
    def __init__( self, socket, address, ioloop, sett ):
        self.socket = socket
        self.address = address
        self.ioloop = ioloop
        self.socket.setblocking(False)

        # configuration settings
        self.max_buffer_size = sett['max_buffer_size']
        self.read_chunk_size = sett['read_chunk_size']

        self._read_buffer = collections.deque()
        self._write_buffer = collections.deque()
        self._read_buffer_size = 0
        self._write_buffer_frozen = False
        self._read_delimiter = None
        self._read_regex = None
        self._read_bytes = None
        self._read_until_close = False
        self._read_callback = None
        self._streaming_callback = None
        self._write_callback = None
        self._close_callback = None
        self._connect_callback = None
        self._connecting = False
        self._state = None
        self._pending_callbacks = 0

    def connect(self, address, callback=None):
        """Connects the socket to a remote address without blocking.

        May only be called if the socket passed to the constructor was
        not previously connected.  The address parameter is in the
        same format as for socket.connect, i.e. a (host, port) tuple.
        If callback is specified, it will be called when the
        connection is completed.

        Note that it is safe to call HTTPIOStream.write while the
        connection is pending, in which case the data will be written
        as soon as the connection is ready.  Calling HTTPIOStream read
        methods before the socket is connected works on some platforms
        but is non-portable.
        """
        self._connecting = True
        try:
            self.socket.connect(address)
        except socket.error as e:
            # In non-blocking mode we expect connect() to raise an
            # exception with EINPROGRESS or EWOULDBLOCK.
            #
            # On freebsd, other errors such as ECONNREFUSED may be
            # returned immediately when attempting to connect to
            # localhost, so handle them the same way as an error
            # reported later in _handle_connect.
            if e.args[0] not in (errno.EINPROGRESS, errno.EWOULDBLOCK):
                #log.warning( 
                #    "Connect error on fd %d: %s", self.socket.fileno(), e )
                self.close()
                return
        self._connect_callback = sc.wrap(callback)
        self._add_io_state(self.ioloop.WRITE)

    def read_until_regex(self, regex, callback):
        """Call callback when we read the given regex pattern."""
        self._set_read_callback(callback)
        self._read_regex = re.compile(regex)
        self._try_inline_read()

    def read_until(self, delimiter, callback):
        """Call callback when we read the given delimiter."""
        self._set_read_callback(callback)
        self._read_delimiter = delimiter
        self._try_inline_read()

    def read_bytes(self, num_bytes, callback, streaming_callback=None):
        """Call callback when we read the given number of bytes.

        If a ``streaming_callback`` is given, it will be called with chunks
        of data as they become available, and the argument to the final
        ``callback`` will be empty.
        """
        self._set_read_callback(callback)
        assert isinstance(num_bytes, int)
        self._read_bytes = num_bytes
        self._streaming_callback = sc.wrap(streaming_callback)
        self._try_inline_read()

    def read_until_close(self, callback, streaming_callback=None):
        """Reads all data from the socket until it is closed.

        If a ``streaming_callback`` is given, it will be called with chunks
        of data as they become available, and the argument to the final
        ``callback`` will be empty.

        Subject to ``max_buffer_size`` limit if a ``streaming_callback`` is 
        not used.
        """
        self._set_read_callback(callback)
        if self.closed():
            self._run_callback(callback, self._consume(self._read_buffer_size))
            self._read_callback = None
            return
        self._read_until_close = True
        self._streaming_callback = sc.wrap(streaming_callback)
        self._add_io_state(self.ioloop.READ)

    def write(self, data, callback=None):
        """Write the given data to this stream.

        If callback is given, we call it when all of the buffered write
        data has been successfully written to the stream. If there was
        previously buffered write data and an old write callback, that
        callback is simply overwritten with this new callback.
        """
        assert isinstance(data, bytes)
        self._check_closed()
        if data:
            # We use bool(_write_buffer) as a proxy for write_buffer_size>0,
            # so never put empty strings in the buffer.
            self._write_buffer.append(data)
        self._write_callback = sc.wrap(callback)
        self._handle_write()
        if self._write_buffer:
            self._add_io_state(self.ioloop.WRITE)
        self._maybe_add_error_listener()

    def set_close_callback(self, callback):
        """Call the given callback when the stream is closed."""
        self._close_callback = sc.wrap(callback)

    def close(self):
        """Close this stream."""
        #log.debug( "Closing the stream from %r ...", self.address )
        if self.socket is not None:
            if self._read_until_close:
                callback = self._read_callback
                self._read_callback = None
                self._read_until_close = False
                self._run_callback(callback,
                                   self._consume(self._read_buffer_size))
            if self._state is not None:
                self.ioloop.remove_handler(self.socket.fileno())
                self._state = None
            self.socket.close()
            self.socket = None
        self._maybe_run_close_callback()

    def _maybe_run_close_callback(self):
        if (self.socket is None and self._close_callback and
            self._pending_callbacks == 0):
            # if there are pending callbacks, don't run the close callback
            # until they're done (see _maybe_add_error_handler)
            cb = self._close_callback
            self._close_callback = None
            self._run_callback(cb)

    def reading(self):
        """Returns true if we are currently reading from the stream."""
        return self._read_callback is not None

    def writing(self):
        """Returns true if we are currently writing to the stream."""
        return bool(self._write_buffer)

    def closed(self):
        """Returns true if the stream has been closed."""
        return self.socket is None

    def _handle_events(self, fd, events):
        if not self.socket:
            #log.warning( "Got events for closed stream %d", fd )
            return
        try:
            if events & self.ioloop.READ:
                self._handle_read()
            if not self.socket:
                return
            if events & self.ioloop.WRITE:
                if self._connecting:
                    self._handle_connect()
                self._handle_write()
            if not self.socket:
                return
            if events & self.ioloop.ERROR:
                # We may have queued up a user callback in _handle_read or
                # _handle_write, so don't close the HTTPIOStream until those
                # callbacks have had a chance to run.
                self.ioloop.add_callback(self.close)
                return
            state = self.ioloop.ERROR
            if self.reading():
                state |= self.ioloop.READ
            if self.writing():
                state |= self.ioloop.WRITE
            if state == self.ioloop.ERROR:
                state |= self.ioloop.READ
            if state != self._state:
                assert self._state is not None, \
                    "shouldn't happen: _handle_events without self._state"
                self._state = state
                self.ioloop.update_handler(self.socket.fileno(), self._state)
        except Exception:
            #log.error( "Uncaught exception, closing connection.", exc_info=True )
            self.close()
            raise

    def _run_callback(self, callback, *args):
        def wrapper():
            self._pending_callbacks -= 1
            try:
                callback(*args)
            except Exception:
                #log.error(
                #    "Uncaught exception, closing connection.", exc_info=True )
                # Close the socket on an uncaught exception from a user 
                # callback (It would eventually get closed when the socket 
                # object is gc'd, but we don't want to rely on gc happening 
                # before we run out of file descriptors)
                self.close()
                # Re-raise the exception so that 
                # HTTPIOLoop.handle_callback_exception can see it and log the 
                # error
                raise
            self._maybe_add_error_listener()
        # We schedule callbacks to be run on the next HTTPIOLoop iteration
        # rather than running them directly for several reasons:
        # * Prevents unbounded stack growth when a callback calls an
        #   HTTPIOLoop operation that immediately runs another callback
        # * Provides a predictable execution context for e.g.
        #   non-reentrant mutexes
        # * Ensures that the try/except in wrapper() is run outside
        #   of the application's StackContexts
        with sc.NullContext():
            # stack_context was already captured in callback, we don't need to
            # capture it again for HTTPIOStream's wrapper.  This is especially
            # important if the callback was pre-wrapped before entry to
            # HTTPIOStream (as in HTTPConnection._header_callback), as we could
            # capture and leak the wrong context here.
            self._pending_callbacks += 1
            self.ioloop.add_callback(wrapper)

    def _handle_read(self):
        try:
            try:
                # Pretend to have a pending callback so that an EOF in
                # _read_to_buffer doesn't trigger an immediate close
                # callback.  At the end of this method we'll either
                # estabilsh a real pending callback via
                # _read_from_buffer or run the close callback.
                #
                # We need two try statements here so that
                # pending_callbacks is decremented before the `except`
                # clause below (which calls `close` and does need to
                # trigger the callback)
                self._pending_callbacks += 1
                while True:
                    # Read from the socket until we get EWOULDBLOCK or equivalent.
                    # SSL sockets do some internal buffering, and if the data is
                    # sitting in the SSL object's buffer select() and friends
                    # can't see it; the only way to find out if it's there is to
                    # try to read it.
                    if self._read_to_buffer() == 0:
                        break
            finally:
                self._pending_callbacks -= 1
        except Exception:
            #log.warning( "error on read", exc_info=True )
            self.close()
            return
        if self._read_from_buffer():
            return
        else:
            self._maybe_run_close_callback()


    def _set_read_callback(self, callback):
        assert not self._read_callback, "Already reading"
        self._read_callback = callback

    def _try_inline_read(self):
        """Attempt to complete the current read operation from buffered data.

        If the read can be completed without blocking, schedules the
        read callback on the next HTTPIOLoop iteration; otherwise starts
        listening for reads on the socket.
        """
        # See if we've already got the data from a previous read
        if self._read_from_buffer():
            return
        self._check_closed()
        while True:
            if self._read_to_buffer() == 0:
                break
            self._check_closed()
        if self._read_from_buffer():
            return
        self._add_io_state(self.ioloop.READ)

    def _read_from_socket(self):
        """Attempts to read from the socket.

        Returns the data read or None if there is nothing to read.
        May be overridden in subclasses.
        """
        try:
            chunk = self.socket.recv( self.read_chunk_size )
        except socket.error as e:
            if e.args[0] in (errno.EWOULDBLOCK, errno.EAGAIN):
                return None
            else:
                raise
        if not chunk : # May be the remote end closed
            self.close()
            return None
        return chunk

    def _read_to_buffer(self):
        """Reads from the socket and appends the result to the read buffer.

        Returns the number of bytes read.  Returns 0 if there is nothing
        to read (i.e. the read returns EWOULDBLOCK or equivalent).  On
        error closes the socket and raises an exception.
        """
        try:
            chunk = self._read_from_socket()
        except socket.error as e:
            # ssl.SSLError is a subclass of socket.error
            #log.warning( "Read error on %d: %s", self.socket.fileno(), e )
            self.close()
            raise
        if chunk is None:
            return 0
        self._read_buffer.append(chunk)
        self._read_buffer_size += len(chunk)
        if self._read_buffer_size >= self.max_buffer_size :
            #log.error( "Reached maximum read buffer size" )
            self.close()
            raise IOError("Reached maximum read buffer size")
        return len(chunk)

    def _read_from_buffer(self):
        """Attempts to complete the currently-pending read from the buffer.

        Returns True if the read was completed.
        """
        if self._streaming_callback is not None and self._read_buffer_size:
            bytes_to_consume = self._read_buffer_size
            if self._read_bytes is not None:
                bytes_to_consume = min(self._read_bytes, bytes_to_consume)
                self._read_bytes -= bytes_to_consume
            self._run_callback(self._streaming_callback,
                               self._consume(bytes_to_consume))
        if self._read_bytes is not None and self._read_buffer_size >= self._read_bytes:
            num_bytes = self._read_bytes
            callback = self._read_callback
            self._read_callback = None
            self._streaming_callback = None
            self._read_bytes = None
            self._run_callback(callback, self._consume(num_bytes))
            return True
        elif self._read_delimiter is not None:
            # Multi-byte delimiters (e.g. '\r\n') may straddle two
            # chunks in the read buffer, so we can't easily find them
            # without collapsing the buffer.  However, since protocols
            # using delimited reads (as opposed to reads of a known
            # length) tend to be "line" oriented, the delimiter is likely
            # to be in the first few chunks.  Merge the buffer gradually
            # since large merges are relatively expensive and get undone in
            # consume().
            if self._read_buffer:
                while True:
                    loc = self._read_buffer[0].find(self._read_delimiter)
                    if loc != -1:
                        callback = self._read_callback
                        delimiter_len = len(self._read_delimiter)
                        self._read_callback = None
                        self._streaming_callback = None
                        self._read_delimiter = None
                        self._run_callback(callback,
                                           self._consume(loc + delimiter_len))
                        return True
                    if len(self._read_buffer) == 1:
                        break
                    _double_prefix(self._read_buffer)
        elif self._read_regex is not None:
            if self._read_buffer:
                while True:
                    m = self._read_regex.search(self._read_buffer[0])
                    if m is not None:
                        callback = self._read_callback
                        self._read_callback = None
                        self._streaming_callback = None
                        self._read_regex = None
                        self._run_callback(callback, self._consume(m.end()))
                        return True
                    if len(self._read_buffer) == 1:
                        break
                    _double_prefix(self._read_buffer)
        return False

    def _handle_connect(self):
        err = self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
        if err != 0:
            # HTTPIOLoop implementations may vary: some of them return
            # an error state before the socket becomes writable, so
            # in that case a connection failure would be handled by the
            # error path in _handle_events instead of here.

            #log.warning( 
            #    "Connect error on fd %d: %s", self.socket.fileno(), 
            #    errno.errorcode[err] )
            self.close()
            return
        if self._connect_callback is not None:
            callback = self._connect_callback
            self._connect_callback = None
            self._run_callback(callback)
        self._connecting = False

    def _handle_write(self):
        while self._write_buffer:
            try:
                if not self._write_buffer_frozen:
                    # On windows, socket.send blows up if given a
                    # write buffer that's too large, instead of just
                    # returning the number of bytes it was able to
                    # process.  Therefore we must not call socket.send
                    # with more than 128KB at a time.
                    _merge_prefix(self._write_buffer, 128 * 1024)
                num_bytes = self.socket.send(self._write_buffer[0])
                if num_bytes == 0:
                    # With OpenSSL, if we couldn't write the entire buffer,
                    # the very same string object must be used on the
                    # next call to send.  Therefore we suppress
                    # merging the write buffer after an incomplete send.
                    # A cleaner solution would be to set
                    # SSL_MODE_ACCEPT_MOVING_WRITE_BUFFER, but this is
                    # not yet accessible from python
                    # (http://bugs.python.org/issue8240)
                    self._write_buffer_frozen = True
                    break
                self._write_buffer_frozen = False
                _merge_prefix(self._write_buffer, num_bytes)
                self._write_buffer.popleft()
            except socket.error as e:
                if e.args[0] in (errno.EWOULDBLOCK, errno.EAGAIN):
                    self._write_buffer_frozen = True
                    break
                else:
                    #log.warning(
                    #        "Write error on %d: %s", self.socket.fileno(), e )
                    self.close()
                    return
        if not self._write_buffer and self._write_callback:
            callback = self._write_callback
            self._write_callback = None
            self._run_callback(callback)

    def _consume(self, loc):
        if loc == 0:
            return b""
        _merge_prefix(self._read_buffer, loc)
        self._read_buffer_size -= loc
        return self._read_buffer.popleft()

    def _check_closed(self):
        if not self.socket:
            raise IOError("Stream is closed")

    def _maybe_add_error_listener(self):
        if self._state is None and self._pending_callbacks == 0:
            if self.socket is None:
                self._maybe_run_close_callback()
            else:
                self._add_io_state(self.ioloop.READ)

    def _add_io_state(self, state):
        """Adds `state` (HTTPIOLoop.{READ,WRITE} flags) to our event handler.

        Implementation notes: Reads and writes have a fast path and a
        slow path.  The fast path reads synchronously from socket
        buffers, while the slow path uses `_add_io_state` to schedule
        an HTTPIOLoop callback.  Note that in both cases, the callback is
        run asynchronously with `_run_callback`.

        To detect closed connections, we must have called
        `_add_io_state` at some point, but we want to delay this as
        much as possible so we don't have to set an `HTTPIOLoop.ERROR`
        listener that will be overwritten by the next slow-path
        operation.  As long as there are callbacks scheduled for
        fast-path ops, those callbacks may do more reads.
        If a sequence of fast-path ops do not end in a slow-path op,
        (e.g. for an @asynchronous long-poll request), we must add
        the error handler.  This is done in `_run_callback` and `write`
        (since the write callback is optional so we can have a
        fast-path write with no `_run_callback`)
        """
        if self.socket is None:
            # connection has been closed, so there can be no future events
            return
        if self._state is None:
            self._state = self.ioloop.ERROR | state
            with sc.NullContext():
                self.ioloop.add_handler(
                    self.socket.fileno(), self._handle_events, self._state)
        elif not self._state & state:
            self._state = self._state | state
            self.ioloop.update_handler(self.socket.fileno(), self._state)


class HTTPSSLIOStream( HTTPIOStream ):
    """A utility class to write to and read from a non-blocking SSL socket.

    If the socket passed to the constructor is already connected,
    it should be wrapped with::

        ssl.wrap_socket(sock, do_handshake_on_connect=False, **kwargs)

    before constructing the HTTPSSLIOStream.  Unconnected sockets will be
    wrapped when HTTPIOStream.connect is finished.
    """
    def __init__( self, *args, **kwargs ):
        """Creates an HTTPSSLIOStream.

        If a dictionary is provided as keyword argument ssloptions,
        it will be used as additional keyword arguments to ssl.wrap_socket.
        """
        self.ssloptions = kwargs.pop('ssloptions', {})
        super().__init__( *args, **kwargs )
        self._ssl_accepting = True
        self._handshake_reading = False
        self._handshake_writing = False

    def reading(self):
        return self._handshake_reading or HTTPSSLIOStream.reading(self)

    def writing(self):
        return self._handshake_writing or HTTPSSLIOStream.writing(self)

    def _do_ssl_handshake(self):
        # Based on code from test_ssl.py in the python stdlib
        try:
            self._handshake_reading = False
            self._handshake_writing = False
            self.socket.do_handshake()
        except ssl.SSLError as err:
            if err.args[0] == ssl.SSL_ERROR_WANT_READ:
                self._handshake_reading = True
                return
            elif err.args[0] == ssl.SSL_ERROR_WANT_WRITE:
                self._handshake_writing = True
                return
            elif err.args[0] in (ssl.SSL_ERROR_EOF,
                                 ssl.SSL_ERROR_ZERO_RETURN):
                return self.close()
            elif err.args[0] == ssl.SSL_ERROR_SSL:
                #log.warning( "SSL Error on %d: %s", self.socket.fileno(), err )
                return self.close()
            raise
        except socket.error as err:
            if err.args[0] == errno.ECONNABORTED:
                return self.close()
        else:
            self._ssl_accepting = False
            HTTPSSLIOStream._handle_connect(self)

    def _handle_read(self):
        if self._ssl_accepting:
            self._do_ssl_handshake()
            return
        HTTPSSLIOStream._handle_read(self)

    def _handle_write(self):
        if self._ssl_accepting:
            self._do_ssl_handshake()
            return
        HTTPSSLIOStream._handle_write(self)

    def _handle_connect(self):
        self.socket = ssl.wrap_socket(self.socket,
                                      do_handshake_on_connect=False,
                                      **self.ssloptions)
        # Don't call the superclass's _handle_connect (which is responsible
        # for telling the application that the connection is complete)
        # until we've completed the SSL handshake (so certificates are
        # available, etc).

    def _read_from_socket(self):
        if self._ssl_accepting:
            # If the handshake hasn't finished yet, there can't be anything
            # to read (attempting to read may or may not raise an exception
            # depending on the SSL version)
            return None
        try:
            # SSLSocket objects have both a read() and recv() method,
            # while regular sockets only have recv().
            # The recv() method blocks (at least in python 2.6) if it is
            # called when there is nothing to read, so we have to use
            # read() instead.
            chunk = self.socket.read( self.read_chunk_size )
        except ssl.SSLError as e:
            # SSLError is a subclass of socket.error, so this except
            # block must come first.
            if e.args[0] == ssl.SSL_ERROR_WANT_READ:
                return None
            else:
                raise
        except socket.error as e:
            if e.args[0] in (errno.EWOULDBLOCK, errno.EAGAIN):
                return None
            else:
                raise
        if not chunk:
            self.close()
            return None
        return chunk

def _double_prefix(deque):
    """Grow by doubling, but don't split the second chunk just because the
    first one is small.
    """
    new_len = max(len(deque[0]) * 2,
                  (len(deque[0]) + len(deque[1])))
    _merge_prefix(deque, new_len)


def _merge_prefix(deque, size):
    """Replace the first entries in a deque of strings with a single
    string of up to size bytes.

    >>> d = collections.deque(['abc', 'de', 'fghi', 'j'])
    >>> _merge_prefix(d, 5); print d
    deque(['abcde', 'fghi', 'j'])

    Strings will be split as necessary to reach the desired size.
    >>> _merge_prefix(d, 7); print d
    deque(['abcdefg', 'hi', 'j'])

    >>> _merge_prefix(d, 3); print d
    deque(['abc', 'defg', 'hi', 'j'])

    >>> _merge_prefix(d, 100); print d
    deque(['abcdefghij'])
    """
    if len(deque) == 1 and len(deque[0]) <= size:
        return
    prefix = []
    remaining = size
    while deque and remaining > 0:
        chunk = deque.popleft()
        if len(chunk) > remaining:
            deque.appendleft(chunk[remaining:])
            chunk = chunk[:remaining]
        prefix.append(chunk)
        remaining -= len(chunk)
    # This data structure normally just contains byte strings, but
    # the unittest gets messy if it doesn't use the default str() type,
    # so do the merge based on the type of data that's actually present.
    if prefix:
        deque.appendleft(type(prefix[0])().join(prefix))
    if not deque:
        deque.appendleft(b"")
