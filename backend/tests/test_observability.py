import unittest
from app.services.observability import (
    mask_text,
    is_langfuse_enabled,
    start_chat_trace,
    trace_step_span,
    record_feedback_score
)


class TestObservability(unittest.TestCase):

    def test_mask_text_emails_and_phones(self):
        sample = "Contact John at john.doe@calispec.ai or call +1 555-123-4567 or 9876543210."
        masked = mask_text(sample)
        self.assertNotIn("john.doe@calispec.ai", masked)
        self.assertNotIn("555-123-4567", masked)
        self.assertNotIn("9876543210", masked)
        self.assertIn("[EMAIL]", masked)
        self.assertIn("[PHONE]", masked)

    def test_trace_and_span_safety(self):
        trace = start_chat_trace(
            user_query="Who is the manager at Delphi?",
            user_id="test_user@example.com",
            session_id="test_sess_123"
        )
        self.assertIsNotNone(trace)

        with trace_step_span(trace, name="unit_test_span") as span:
            span.update(output={"status": "ok"}, metadata={"test": True})

        trace.score("test_score", 1.0)
        trace.end(output={"summary": "done"})

    def test_feedback_score_recording(self):
        # Must not raise exceptions
        record_feedback_score(
            session_id="test_sess_123",
            value=1.0,
            comment="Great answer! Contact user@test.com",
            user_id="test_user"
        )


if __name__ == "__main__":
    unittest.main()
