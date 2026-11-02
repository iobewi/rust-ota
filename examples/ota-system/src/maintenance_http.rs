//! HTTP rejection shared by both reference maintenance handlers.
//!
//! No flash access, allocations, or application state are needed on this path.
use picoserve::{
    ResponseSent,
    io::Read,
    request::Request,
    response::{IntoResponse, ResponseWriter, StatusCode},
};

/// Budget for receiving headers and ordinary requests, without authentication.
pub const REQUEST_TIMEOUT_SECS: u64 = 3;
/// Absolute body-read budget granted only after successful authorization.
pub const UPLOAD_TIMEOUT_SECS: u64 = 120;

/// One request per connection prevents persistent peers monopolizing the single
/// reference server. Transport handshake and rate limiting remain product policy.
pub fn configure(config: &mut picoserve::Config) {
    config.connection = picoserve::KeepAlive::Close;
    config.timeouts.read_request = picoserve::time::Duration::from_secs(REQUEST_TIMEOUT_SECS);
}

/// Reject without waiting for unreceived body bytes. With picoserve 0.20 an
/// unread body would otherwise be drained by `finalize` before sending a 401.
/// Consume only already-buffered bytes using an immediately expired body reader.
/// If bytes are missing, propagate the read timeout: the server closes the
/// connection without a response. Otherwise send 401 through the normal writer.
/// This deliberately does not grant an unauthenticated peer an upload deadline.
pub async fn reject_unauthorized<R: Read, W: ResponseWriter<Error = R::Error>>(
    mut request: Request<'_, R>,
    writer: W,
) -> Result<ResponseSent, W::Error> {
    {
        let mut reader = request
            .body_connection
            .body()
            .reader()
            .with_different_timeout_signal(core::future::ready(()));
        let mut scratch = [0; 64];
        while reader.read(&mut scratch).await? != 0 {}
    }
    (StatusCode::UNAUTHORIZED, "unauthorized")
        .write_to(request.body_connection.finalize().await?, writer)
        .await
}

#[cfg(test)]
mod tests;
