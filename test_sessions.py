import unittest

from document_intelligence.sessions import SessionManager


class SessionManagerTests(unittest.TestCase):
    def test_creates_deduplicated_scope(self) -> None:
        manager = SessionManager()
        session = manager.create(["first", "first", "second"])
        self.assertEqual(session.document_ids, ["first", "second"])

    def test_completes_message_and_bounds_history(self) -> None:
        manager = SessionManager(max_history_messages=2)
        session = manager.create(["first"])
        manager.begin_message(session.id)
        manager.complete_message(session.id, "Question one", "Answer one")
        manager.begin_message(session.id)
        manager.complete_message(session.id, "Question two", "Answer two")
        self.assertEqual(
            manager.get(session.id).history,
            [
                {"role": "user", "content": "Question two"},
                {"role": "assistant", "content": "Answer two"},
            ],
        )

    def test_rejects_concurrent_message(self) -> None:
        manager = SessionManager()
        session = manager.create(["first"])
        manager.begin_message(session.id)
        with self.assertRaisesRegex(RuntimeError, "processing another message"):
            manager.begin_message(session.id)

    def test_reselection_clears_history(self) -> None:
        manager = SessionManager()
        session = manager.create(["first"])
        manager.begin_message(session.id)
        manager.complete_message(session.id, "Question", "Answer")
        manager.update_documents(session.id, ["second"])
        self.assertEqual(manager.get(session.id).history, [])

    def test_delete_removes_session(self) -> None:
        manager = SessionManager()
        session = manager.create(["first"])
        manager.delete(session.id)
        with self.assertRaises(KeyError):
            manager.get(session.id)


if __name__ == "__main__":
    unittest.main()
