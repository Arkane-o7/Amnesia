import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from backend import codex_provider
from backend.engine import diagnostics, embeddings, structured, consume_trace

CONFIG = {'provider': 'codex', 'chat_model': 'gpt-5.6-sol', 'embedding_model': 'nomic-embed-text:latest', 'ollama_url': 'http://127.0.0.1:11435'}
SCHEMA = {'type': 'object', 'properties': {'ready': {'type': 'boolean'}}, 'required': ['ready'], 'additionalProperties': False}


class CodexProviderTests(unittest.TestCase):
    def test_rate_limit_is_explicit_and_uses_longer_bounded_backoff(self):
        reply = (1, [{'type': 'turn.failed', 'error': {'message': '429 Too Many Requests'}}], None, '')
        with patch('backend.codex_provider.subprocess.Popen', side_effect=self.fake_launch([reply, reply])) as call, patch('backend.codex_provider.time.sleep') as sleep:
            with self.assertRaisesRegex(codex_provider.InferenceError, 'rate limit reached') as caught:
                codex_provider.run([], SCHEMA, 'test', CONFIG)
        self.assertEqual(caught.exception.category, 'rate_limit')
        self.assertEqual(call.call_count, 2)
        sleep.assert_called_once_with(5)

    def test_stderr_timestamp_is_not_an_http_status(self):
        error = codex_provider.classify_failure([], '2026-10-21T03:03:22.503 WARN startup diagnostic', 1)
        self.assertEqual(error.category, 'unknown')
        self.assertFalse(error.retryable)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict('os.environ', {'AMNESIA_DATA_DIR': self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def fake_launch(self, replies):
        def launch(args, **kwargs):
            code, events, answer, stderr = replies.pop(0)
            if answer is not None:
                Path(args[args.index('--output-last-message')+1]).write_text(answer)
            process = MagicMock(returncode=code)
            process.communicate.return_value = ('\n'.join(json.dumps(e) for e in events), stderr)
            return process
        return launch

    def test_recovered_stream_error_with_completed_valid_output_is_success(self):
        replies = [(0, [{'type': 'error', 'message': 'Reconnecting: stream disconnected'}, {'type': 'turn.completed', 'usage': {}}], '{"ready":true}', '')]
        with patch('backend.codex_provider.subprocess.Popen', side_effect=self.fake_launch(replies)) as call:
            result, _ = codex_provider.run([], SCHEMA, 'test', CONFIG)
        self.assertTrue(result['ready'])
        self.assertEqual(call.call_count, 1)
        self.assertEqual(json.loads((Path(self.tmp.name)/'diagnostics/codex.jsonl').read_text())['category'], 'recovered')

    def test_temporary_failure_retries_once_and_succeeds(self):
        replies = [(1, [{'type': 'turn.failed', 'error': {'message': '503 Service temporarily unavailable'}}], None, ''),
                   (0, [{'type': 'turn.completed', 'usage': {}}], '{"ready":true}', '')]
        with patch('backend.codex_provider.subprocess.Popen', side_effect=self.fake_launch(replies)) as call, patch('backend.codex_provider.time.sleep'):
            result, _ = codex_provider.run([], SCHEMA, 'test', CONFIG)
        self.assertTrue(result['ready'])
        self.assertEqual(call.call_count, 2)

    def test_temporary_failure_stops_after_two_attempts(self):
        reply = (1, [{'type': 'turn.failed', 'error': {'message': 'Connection reset'}}], None, '')
        with patch('backend.codex_provider.subprocess.Popen', side_effect=self.fake_launch([reply, reply])) as call, patch('backend.codex_provider.time.sleep'):
            with self.assertRaisesRegex(ValueError, 'Diagnostic:'):
                codex_provider.run([], SCHEMA, 'test', CONFIG)
        self.assertEqual(call.call_count, 2)

    def test_auth_quota_model_and_unknown_failures_do_not_retry(self):
        for message, category in [('401 Unauthorized', 'authentication'), ('usage limit reached', 'quota'), ('model_not_found', 'configuration'), ('unspecified failure', 'unknown')]:
            with self.subTest(category=category), patch('backend.codex_provider.subprocess.Popen', side_effect=self.fake_launch([(1, [{'type': 'turn.failed', 'error': {'message': message}}], None, '')])) as call:
                with self.assertRaises(codex_provider.InferenceError) as caught:
                    codex_provider.run([], SCHEMA, 'test', CONFIG)
                self.assertEqual(caught.exception.category, category)
                self.assertEqual(call.call_count, 1)

    def test_terminal_failure_cannot_use_earlier_completed_output(self):
        replies = [(1, [{'type': 'turn.completed'}, {'type': 'turn.failed', 'error': {'message': 'Unknown failure'}}], '{"ready":true}', '')]
        with patch('backend.codex_provider.subprocess.Popen', side_effect=self.fake_launch(replies)):
            with self.assertRaises(codex_provider.InferenceError):
                codex_provider.run([], SCHEMA, 'test', CONFIG)

    def test_retry_cannot_reuse_stale_answer_file(self):
        replies = [(1, [{'type': 'turn.failed', 'error': {'message': '503'}}], '{"ready":true}', ''),
                   (0, [{'type': 'turn.completed'}], None, '')]
        with patch('backend.codex_provider.subprocess.Popen', side_effect=self.fake_launch(replies)), patch('backend.codex_provider.time.sleep'):
            with self.assertRaisesRegex(ValueError, 'complete structured answer'):
                codex_provider.run([], SCHEMA, 'test', CONFIG)

    def test_diagnostics_redact_secrets_and_exclude_prompt_and_answer(self):
        replies = [(1, [{'type': 'turn.failed', 'error': {'message': '401 Authorization: Bearer secret-token access_token=abc123 sk-secretkey'}}], '{"private":"answer-value"}', '')]
        with patch('backend.codex_provider.subprocess.Popen', side_effect=self.fake_launch(replies)):
            with self.assertRaises(ValueError):
                codex_provider.run([{'content': 'private-input'}], SCHEMA, 'test', CONFIG)
        file = Path(self.tmp.name)/'diagnostics/codex.jsonl'
        content = file.read_text()
        for secret in ('secret-token', 'abc123', 'sk-secretkey', 'private-input', 'answer-value'):
            self.assertNotIn(secret, content)
        self.assertEqual(file.stat().st_mode & 0o777, 0o600)

    def test_cli_auth_status_uses_chatgpt_login_without_reading_credentials(self):
        with patch('backend.codex_provider.shutil.which', return_value='/official/codex'), patch('backend.codex_provider.subprocess.run', side_effect=[subprocess.CompletedProcess([], 0, '', 'Logged in using ChatGPT'), subprocess.CompletedProcess([], 0, 'codex-cli 0.149.1', '')]) as call:
            result = codex_provider.login_status()
            self.assertTrue(result['codex_authenticated'])
            self.assertEqual(call.call_args_list[0].args[0], ['/official/codex', 'login', 'status'])

    def test_api_key_login_is_not_mislabeled_as_chatgpt_subscription(self):
        with patch('backend.codex_provider.shutil.which', return_value='/official/codex'), patch('backend.codex_provider.subprocess.run', side_effect=[subprocess.CompletedProcess([], 0, '', 'Logged in using an API key'), subprocess.CompletedProcess([], 0, 'codex-cli 0.149.1', '')]):
            self.assertFalse(codex_provider.login_status()['codex_authenticated'])

    def test_codex_command_is_ephemeral_and_tool_access_is_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            command = codex_provider.command('/official/codex', Path(directory), CONFIG['chat_model'])
            for flag in ('--ephemeral', '--ignore-user-config', '--ignore-rules', '--output-schema', '--json'):
                self.assertIn(flag, command)
            self.assertEqual(command[command.index('--sandbox')+1], 'read-only')
            for feature in ('shell_tool', 'multi_agent', 'apps', 'plugins', 'hooks'):
                i = command.index(feature)
                self.assertEqual(command[i-1], '--disable')

    def test_subprocess_answer_requires_successful_completion_and_reports_usage(self):
        process = MagicMock(returncode=0)
        def launch(args, **kwargs):
            Path(args[args.index('--output-last-message')+1]).write_text('{"ready":true}')
            process.communicate.return_value = (json.dumps({'type': 'item.completed', 'item': {'type': 'error', 'message': 'Non-fatal startup diagnostic'}})+'\n'+json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 30, 'output_tokens': 5}})+'\n', '')
            return process
        with patch('backend.codex_provider.shutil.which', return_value='/official/codex'), patch('backend.codex_provider.subprocess.Popen', side_effect=launch):
            result, usage = codex_provider.run([{'role': 'user', 'content': 'ready'}], SCHEMA, 'test', CONFIG)
            self.assertTrue(result['ready'])
            self.assertEqual(usage['input_tokens'], 30)

    def test_tool_event_is_rejected_even_when_last_message_is_json(self):
        process = MagicMock(returncode=0)
        process.communicate.return_value = (json.dumps({'type': 'item.completed', 'item': {'type': 'command_execution'}})+'\n'+json.dumps({'type': 'turn.completed', 'usage': {}}), '')
        with patch('backend.codex_provider.shutil.which', return_value='/official/codex'), patch('backend.codex_provider.subprocess.Popen', return_value=process):
            with self.assertRaisesRegex(ValueError, 'tool action'):
                codex_provider.run([], SCHEMA, 'test', CONFIG)

    def test_incomplete_turn_is_not_reported_as_success(self):
        process = MagicMock(returncode=0)
        process.communicate.return_value = ('{"type":"turn.started"}\n', '')
        with patch('backend.codex_provider.shutil.which', return_value='/official/codex'), patch('backend.codex_provider.subprocess.Popen', return_value=process):
            with self.assertRaisesRegex(ValueError, 'inference failed'):
                codex_provider.run([], SCHEMA, 'test', CONFIG)

    def test_codex_text_routes_to_cli_and_embeddings_stay_local(self):
        consume_trace()
        with patch('backend.codex_provider.run', return_value=({'ready': True}, {'input_tokens': 40, 'output_tokens': 5})), patch('backend.engine.cloud_key', side_effect=AssertionError('No API key needed')):
            self.assertTrue(structured([], SCHEMA, 'test', CONFIG)['ready'])
        self.assertEqual(consume_trace()[0]['input_tokens'], 40)
        with patch('backend.engine.request_json', return_value={'embeddings': [[1, 0]]}) as request:
            self.assertEqual(embeddings(['memory'], CONFIG), [[1, 0]])
            self.assertTrue(request.call_args.args[0].startswith('http://127.0.0.1:11435/'))

    def test_readiness_checks_only_local_embeddings_and_codex_login(self):
        with patch('backend.codex_provider.login_status', return_value={'codex_authenticated': True, 'cli_version': 'codex-cli 0.149.1', 'message': 'Signed in.'}), patch('backend.engine.request_json', return_value={'models': [{'name': 'nomic-embed-text:latest'}]}):
            self.assertTrue(diagnostics(CONFIG)['ready'])

    def test_api_key_and_parent_thread_are_not_inherited_by_codex(self):
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'fake-key', 'CODEX_THREAD_ID': 'parent', 'CODEX_INTERNAL_ORIGINATOR_OVERRIDE': 'parent'}):
            environment = codex_provider.child_environment()
            self.assertNotIn('OPENAI_API_KEY', environment)
            self.assertNotIn('CODEX_THREAD_ID', environment)
            self.assertNotIn('CODEX_INTERNAL_ORIGINATOR_OVERRIDE', environment)

    def test_timed_out_codex_process_is_terminated_as_a_group(self):
        process = MagicMock(returncode=1, pid=12345)
        process.communicate.side_effect = [subprocess.TimeoutExpired('codex', 1), ('', '')]
        with patch('backend.codex_provider.shutil.which', return_value='/official/codex'), patch('backend.codex_provider.subprocess.Popen', return_value=process), patch('backend.codex_provider.os.killpg') as terminate:
            with self.assertRaisesRegex(ValueError, 'timed out'):
                codex_provider.run([], SCHEMA, 'test', CONFIG, timeout=1)
            terminate.assert_called_once_with(12345, codex_provider.signal.SIGTERM)


if __name__ == '__main__':
    unittest.main()
