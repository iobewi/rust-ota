use super::*;
use core::{
    cell::Cell,
    future::Future,
    task::{Context, Poll, Waker},
};
use picoserve::{
    io::{self, BaseWrite, ErrorType},
    mem::{BorrowedBuffer, BorrowedCursor},
    routing::RequestHandlerService,
    time::{Duration, Timer},
};
use std::{
    string::{String, ToString},
    vec::Vec,
};

struct Runtime;
struct FrozenTime;
impl Timer<Runtime> for FrozenTime {
    async fn delay(&self, _: Duration) {
        core::future::pending().await
    }
}

struct Rx<'a> {
    bytes: &'a [u8],
    reads: &'a Cell<usize>,
}
impl ErrorType for Rx<'_> {
    type Error = io::ErrorKind;
}
impl Read for Rx<'_> {
    async fn read(&mut self, out: &mut [u8]) -> Result<usize, Self::Error> {
        self.reads.set(self.reads.get() + 1);
        if self.bytes.is_empty() {
            return core::future::pending().await;
        }
        let n = out.len().min(self.bytes.len());
        out[..n].copy_from_slice(&self.bytes[..n]);
        self.bytes = &self.bytes[n..];
        Ok(n)
    }
}
struct Tx<'a>(&'a mut Vec<u8>);
impl ErrorType for Tx<'_> {
    type Error = io::ErrorKind;
}
impl BaseWrite for Tx<'_> {
    async fn write(&mut self, bytes: &[u8]) -> Result<usize, Self::Error> {
        self.0.extend_from_slice(bytes);
        Ok(bytes.len())
    }
    async fn flush(&mut self) -> Result<(), Self::Error> {
        Ok(())
    }
}
impl io::Write for Tx<'_> {
    async fn write_with<F: FnOnce(BorrowedCursor<'_>) -> T, T>(
        &mut self,
        f: F,
    ) -> Result<T, Self::Error> {
        let mut bytes = [0; 1024];
        let mut buffer = BorrowedBuffer::new(&mut bytes);
        let result = f(buffer.unfilled());
        self.0.extend_from_slice(buffer.filled());
        Ok(result)
    }
}
struct Socket<'a> {
    rx: Rx<'a>,
    tx: Vec<u8>,
    closed: &'a Cell<bool>,
}
impl<'data> io::Socket<Runtime> for &mut Socket<'data> {
    type Error = io::ErrorKind;
    type ReadHalf<'a>
        = &'a mut Rx<'data>
    where
        Self: 'a;
    type WriteHalf<'a>
        = Tx<'a>
    where
        Self: 'a;
    fn split(&mut self) -> (Self::ReadHalf<'_>, Self::WriteHalf<'_>) {
        (&mut self.rx, Tx(&mut self.tx))
    }
    async fn abort<T: Timer<Runtime>>(
        self,
        _: &picoserve::Timeouts,
        _: &T,
    ) -> Result<(), picoserve::Error<Self::Error>> {
        self.closed.set(true);
        Ok(())
    }
    async fn shutdown<T: Timer<Runtime>>(
        self,
        _: &picoserve::Timeouts,
        _: &T,
    ) -> Result<(), picoserve::Error<Self::Error>> {
        self.closed.set(true);
        Ok(())
    }
}
struct Handler<'a> {
    mutations: &'a Cell<usize>,
    dispatches: &'a Cell<usize>,
}
impl RequestHandlerService for Handler<'_> {
    async fn call_request_handler_service<R: Read, W: ResponseWriter<Error = R::Error>>(
        &self,
        _: &(),
        (): (),
        mut request: Request<'_, R>,
        writer: W,
    ) -> Result<ResponseSent, W::Error> {
        self.dispatches.set(self.dispatches.get() + 1);
        let token = request
            .parts
            .headers()
            .get("authorization")
            .and_then(|v| v.as_str().ok());
        if !iobewi_firmware_auth::maintenance::token_matches(b"secret", token.map(str::as_bytes)) {
            return reject_unauthorized(request, writer).await;
        }
        let mut reader = request.body_connection.body().reader();
        let mut buffer = [0; 64];
        while reader.read(&mut buffer).await? != 0 {}
        self.mutations.set(self.mutations.get() + 1);
        (StatusCode::OK, "accepted")
            .write_to(request.body_connection.finalize().await?, writer)
            .await
    }
}

// A frozen clock plus one poll makes waiting for the client (or a timeout)
// a deterministic failure, rather than a test depending on wall-clock speed.
fn run(bytes: &[u8]) -> (String, usize, usize, bool) {
    run_observed(bytes, false).0
}

fn run_observed(bytes: &[u8], persistent: bool) -> ((String, usize, usize, bool), usize) {
    let dispatches = Cell::new(0);
    let reads = Cell::new(0);
    let mutations = Cell::new(0);
    let closed = Cell::new(false);
    let mut socket = Socket {
        rx: Rx {
            bytes,
            reads: &reads,
        },
        tx: Vec::new(),
        closed: &closed,
    };
    let router = picoserve::Router::new().route(
        "/",
        picoserve::routing::post_service(Handler {
            mutations: &mutations,
            dispatches: &dispatches,
        }),
    );
    let mut config = picoserve::Config::const_default().keep_connection_alive();
    configure(&mut config);
    if persistent {
        config = config.keep_connection_alive();
    }
    let mut buffer = [0; 2048];
    {
        let server = picoserve::Server::custom(&router, FrozenTime, &config, &mut buffer);
        let future = server.serve(&mut socket);
        let mut future = core::pin::pin!(future);
        assert!(
            matches!(
                future
                    .as_mut()
                    .poll(&mut Context::from_waker(Waker::noop())),
                Poll::Ready(_)
            ),
            "must not wait for client bytes or clock"
        );
    }
    (
        (
            String::from_utf8(socket.tx).unwrap(),
            reads.get(),
            mutations.get(),
            closed.get(),
        ),
        dispatches.get(),
    )
}

#[test]
fn denied_incomplete_body_never_polls_transport_again() {
    for token in ["", "Authorization: wrong\r\n", "Authorization: \r\n"] {
        for length in [4096, 1_572_864, usize::MAX - 2048] {
            let request =
                std::format!("POST / HTTP/1.1\r\n{token}Content-Length: {length}\r\n\r\npartial");
            let (response, reads, mutations, closed) = run(request.as_bytes());
            assert!(response.is_empty());
            assert_eq!(reads, 1);
            assert_eq!(mutations, 0);
            assert!(closed);
        }
    }
}
#[test]
fn denied_complete_or_empty_body_receives_401() {
    for body in ["", "abc"] {
        let request = std::format!(
            "POST / HTTP/1.1\r\nContent-Length: {}\r\n\r\n{body}",
            body.len()
        );
        let (response, reads, mutations, closed) = run(request.as_bytes());
        assert!(response.starts_with("HTTP/1.1 401"), "{response}");
        assert_eq!(reads, 1);
        assert_eq!(mutations, 0);
        assert!(closed);
    }
}
#[test]
fn authorized_upload_still_reaches_application() {
    let (response, _, mutations, closed) =
        run(b"POST / HTTP/1.1\r\nAuthorization: secret\r\nContent-Length: 3\r\n\r\nabc");
    assert!(response.starts_with("HTTP/1.1 200"), "{response}");
    assert_eq!(mutations, 1);
    assert!(closed);
}

#[test]
fn maintenance_config_bounds_unauthenticated_requests_and_disables_keepalive() {
    let mut config = picoserve::Config::const_default().keep_connection_alive();
    configure(&mut config);
    assert!(matches!(config.connection, picoserve::KeepAlive::Close));
    assert_eq!(config.timeouts.read_request.as_secs(), REQUEST_TIMEOUT_SECS);
    assert_eq!(UPLOAD_TIMEOUT_SECS, 120);
}

#[test]
fn denied_pipeline_never_reaches_authorized_followup() {
    let (response, reads, mutations, closed) = run(b"POST / HTTP/1.1\r\nContent-Length: 0\r\n\r\nPOST / HTTP/1.1\r\nAuthorization: secret\r\nContent-Length: 0\r\n\r\n");
    assert_eq!(response.matches("HTTP/1.1").count(), 1);
    assert!(response.starts_with("HTTP/1.1 401"));
    assert_eq!(reads, 1);
    assert_eq!(mutations, 0);
    assert!(closed);
}

#[test]
fn denied_ready_large_body_is_not_drained_from_transport() {
    let request = std::format!(
        "POST / HTTP/1.1\r\nContent-Length: 4096\r\n\r\n{}",
        "x".repeat(4096)
    );
    let (response, reads, mutations, closed) = run(request.as_bytes());
    assert!(response.is_empty());
    assert_eq!(reads, 1);
    assert_eq!(mutations, 0);
    assert!(closed);
}

#[test]
fn authorized_body_can_exceed_http_buffer() {
    let request = std::format!(
        "POST / HTTP/1.1\r\nAuthorization: secret\r\nContent-Length: 4096\r\n\r\n{}",
        "x".repeat(4096)
    );
    let (response, reads, mutations, closed) = run(request.as_bytes());
    assert!(response.starts_with("HTTP/1.1 200"));
    assert!(reads > 1);
    assert_eq!(mutations, 1);
    assert!(closed);
}

#[test]
fn overflowing_content_length_is_400_before_dispatch() {
    for length in [usize::MAX.to_string(), (usize::MAX as u128 + 1).to_string()] {
        let request = std::format!(
            "POST / HTTP/1.1\r\nAuthorization: secret\r\nContent-Length: {length}\r\n\r\nPOST / HTTP/1.1\r\nAuthorization: secret\r\nContent-Length: 0\r\n\r\n"
        );
        let ((response, reads, mutations, closed), dispatches) =
            run_observed(request.as_bytes(), true);
        assert!(response.starts_with("HTTP/1.1 400"), "{response}");
        assert_eq!(response.matches("HTTP/1.1").count(), 1);
        assert_eq!(reads, 1);
        assert_eq!(mutations, 0);
        assert_eq!(dispatches, 0);
        assert!(closed);
    }
}

#[test]
fn request_end_boundary_is_checked_exactly() {
    // Decimal width is identical for these adjacent huge lengths.
    let prefix = std::format!("POST / HTTP/1.1\r\nContent-Length: {}\r\n\r\n", usize::MAX);
    let limit = usize::MAX - prefix.len();
    for (length, expected_dispatches) in [(limit - 1, 1), (limit, 1), (limit + 1, 0)] {
        let request = std::format!("POST / HTTP/1.1\r\nContent-Length: {length}\r\n\r\n");
        assert_eq!(request.len(), prefix.len());
        let ((response, reads, mutations, closed), dispatches) =
            run_observed(request.as_bytes(), true);
        if expected_dispatches == 0 {
            assert!(response.starts_with("HTTP/1.1 400"), "{response}");
        } else {
            // Representable, but unauthenticated and missing its body: reject
            // via the immediate timeout, rather than imposing a new size limit.
            assert!(response.is_empty());
        }
        assert_eq!(dispatches, expected_dispatches);
        assert_eq!(reads, 1);
        assert_eq!(mutations, 0);
        assert!(closed);
    }
}

#[test]
fn invalid_lengths_do_not_become_an_empty_authorized_request() {
    for length in [
        "",
        "+0",
        "-1",
        "NaN",
        "1, 1",
        "99999999999999999999999999999999999999999999",
    ] {
        let request = std::format!(
            "POST / HTTP/1.1\r\nAuthorization: secret\r\nContent-Length: {length}\r\n\r\n"
        );
        let ((response, reads, mutations, closed), dispatches) =
            run_observed(request.as_bytes(), true);
        assert!(response.starts_with("HTTP/1.1 400"), "{length}: {response}");
        assert_eq!((reads, mutations, dispatches), (1, 0, 0));
        assert!(closed);
    }
}

#[test]
fn absent_or_decimal_zero_length_keeps_existing_empty_request_semantics() {
    for header in ["", "Content-Length: 0\r\n", "Content-Length: 000\r\n"] {
        let request = std::format!("POST / HTTP/1.1\r\nAuthorization: secret\r\n{header}\r\n");
        let ((response, reads, mutations, closed), dispatches) =
            run_observed(request.as_bytes(), false);
        assert!(response.starts_with("HTTP/1.1 200"), "{response}");
        assert_eq!((reads, mutations, dispatches), (1, 1, 1));
        assert!(closed);
    }
}

#[test]
fn non_utf8_length_is_rejected_before_dispatch() {
    let ((response, reads, mutations, closed), dispatches) = run_observed(
        b"POST / HTTP/1.1\r\nAuthorization: secret\r\nContent-Length: \xff\r\n\r\n",
        true,
    );
    assert!(response.starts_with("HTTP/1.1 400"), "{response}");
    assert_eq!((reads, mutations, dispatches), (1, 0, 0));
    assert!(closed);
}
