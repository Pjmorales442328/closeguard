# tests/test_app_voice.py — voice routes offline: transcript logs nothing, Ask logs one voice_query, limits, no network.
import os
import tempfile
import unittest
from unittest import mock

try:
    from fastapi.testclient import TestClient
    from app import state
    from app.main import app
    from app.services import voice as sv
except ImportError:
    app = None

HX = {"HX-Request": "true"}
WEBM = b"\x1a\x45\xdf\xa3" + b"\0" * 64


@unittest.skipIf(app is None, "fastapi/httpx not installed (pip install -r requirements.txt)")
class VoiceTest(unittest.TestCase):
    def setUp(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("CG_")}
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env["CG_ATTEMPTS"] = os.path.join(tmp.name, "a.jsonl")
        p = mock.patch.dict(os.environ, env, clear=True)
        p.start()
        self.addCleanup(p.stop)
        sv._HITS.clear()
        self.c = TestClient(app)
        self.rid = self.c.post("/runs?seed=1", follow_redirects=False).headers["location"].rsplit("/", 1)[-1]
        self.run = state.RUNS[self.rid]

    def n_voice(self):
        return sum(e["kind"] == "voice_query" and e["payload"]["run_id"] == self.rid for e in state.CHAIN)

    def ask(self, text, heard=""):
        return self.c.post(f"/runs/{self.rid}/voice/ask", data={"text": text, "heard": heard}, headers=HX)

    def test_why_answer_uses_run_state_and_logs_once(self):
        r = self.ask("Why was B0078 refused?", "why was b zero zero t buy refused")
        d = self.run.decisions["B0078"]
        from app.services import plain
        self.assertIn(plain.reason(d.rule, d.detail), r.text)
        self.assertIn("1,250.00", r.text)
        self.assertEqual(self.n_voice(), 1)
        ev = [e for e in state.CHAIN if e["kind"] == "voice_query" and e["payload"]["run_id"] == self.rid][-1]["payload"]
        self.assertEqual((ev["intent"], ev["line"], ev["heard"]), ("why", "B0078", "why was b zero zero t buy refused"))

    def test_approve_intent_only_fills_form(self):
        r = self.ask("approve all allowed, Maria, controller")
        self.assertIn('data-fill-name="Maria"', r.text)
        self.assertEqual((self.run.approvals, self.run.attempts), ([], []))

    def test_other_intents(self):
        self.assertIn("passed every check and are waiting", self.ask("what is left to approve").text)
        self.assertIn("80 bank lines", self.ask("give me the close summary").text)
        self.assertIn("I can answer", self.ask("tell me a joke").text)

    def test_transcribe_fills_box_and_logs_nothing(self):
        before = len(state.CHAIN)
        with mock.patch.dict(os.environ, {"CG_MODEL_LIVE": "1"}), mock.patch("agent.voice.transcribe", return_value="why was B0078 refused") as t:
            r = self.c.post(f"/runs/{self.rid}/voice/transcribe", files={"audio": ("q.webm", WEBM, "audio/webm")}, headers=HX)
        t.assert_called_once()
        self.assertIn("why was B0078 refused</textarea>", r.text)
        self.assertEqual(len(state.CHAIN), before)

    def test_transcribe_off_without_live_model(self):
        r = self.c.post(f"/runs/{self.rid}/voice/transcribe", files={"audio": ("q.webm", WEBM, "audio/webm")}, headers=HX)
        self.assertIn("Type your question instead", r.text)

    def test_upload_limits(self):
        up = lambda b, m="audio/webm": self.c.post(f"/runs/{self.rid}/voice/transcribe", files={"audio": ("q", b, m)}, headers=HX)
        self.assertEqual(up(WEBM + b"\0" * (2 * 1024 * 1024)).status_code, 413)
        self.assertEqual(up(b"GIF89a" + b"\0" * 20, "image/gif").status_code, 415)

    def test_hourly_budget(self):
        with mock.patch.dict(os.environ, {"CG_VOICE_LIVE_PER_HOUR": "1"}):
            self.assertTrue(sv.take())
            self.assertFalse(sv.take())

    def test_demo_answers_have_committed_audio(self):  # offline server plays these (agent/seed_voice.py made them)
        from agent.seed_voice import QUESTIONS
        for q in QUESTIONS:
            page = self.ask(q).text
            key = page.split("/voice/audio/")[1][:32]
            r = self.c.get(f"/voice/audio/{key}")
            self.assertEqual((r.status_code, r.headers["content-type"]), (200, "audio/mpeg"), q)

    def test_audio_route(self):
        self.assertEqual(self.c.get("/voice/audio/zz").status_code, 404)
        off = self.ask("why was B0003 refused").text  # not in the committed demo audio
        self.assertIn("data-browser-voice", off)  # model off and nothing cached: browser voice, no audio request
        with mock.patch.dict(os.environ, {"CG_MODEL_LIVE": "1"}):
            key = self.ask("why was B0003 refused").text.split("/voice/audio/")[1][:32]
        self.assertEqual(self.c.get(f"/voice/audio/{key}").status_code, 404)  # model off again: no audio
        with mock.patch.dict(os.environ, {"CG_MODEL_LIVE": "1"}), mock.patch("agent.voice.speak", return_value=b"RIFFxxxxWAVE"), \
                mock.patch.object(sv, "VAR_DIR", sv.VAR_DIR.with_name("voice_test_cache")):
            r = self.c.get(f"/voice/audio/{key}")
            self.assertEqual((r.status_code, r.headers["content-type"]), (200, "audio/wav"))
            sv.VAR_DIR.joinpath(f"{key}.wav").unlink()
            sv.VAR_DIR.rmdir()


if __name__ == "__main__":
    unittest.main()
