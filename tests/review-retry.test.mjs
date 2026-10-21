import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const source = await readFile(new URL('../src/reviewProgress.ts', import.meta.url), 'utf8');
const {outputText} = ts.transpileModule(source, {compilerOptions:{target:ts.ScriptTarget.ES2022, module:ts.ModuleKind.ESNext}});
const {createReviewWriter, createReviewConfirmation} = await import('data:text/javascript;base64,' + Buffer.from(outputText).toString('base64'));

test('lost ingestion response retries the same request without creating a separate session', async () => {
  const bodies = [];
  const receipt = {event_id:'e1', session_id:'s2'};
  const writer = createReviewWriter(async (route, body) => {
    assert.equal(route, 'events');
    bodies.push({...body});
    if (bodies.length === 1) throw new Error('Response lost');
    return receipt;
  });
  await assert.rejects(writer.write(2, 'w1', 's1', 'I moved to Chennai.'));
  assert.deepEqual(await writer.write(2, 'w1', 's1', 'I moved to Chennai.'), receipt);
  assert.deepEqual(bodies[0], bodies[1]);
  assert.equal(bodies[1].new_session, true);
  assert.equal(writer.isCommitted(2), true);
  await writer.write(2, 'w1', 's2', 'I moved to Chennai.');
  assert.equal(bodies.length, 2, 'Later query/state failure must not re-ingest');
});

test('editing an uncommitted failed input starts a new request', async () => {
  const bodies = [];
  const writer = createReviewWriter(async (_, body) => { bodies.push(body); throw new Error('failed'); });
  await assert.rejects(writer.write(1, 'w1', 's1', 'old input'));
  await assert.rejects(writer.write(1, 'w1', 's1', 'corrected input'));
  assert.notEqual(bodies[0].request_id, bodies[1].request_id);
  assert.equal(bodies[1].new_session, false);
});


test('answer failure after confirmation can retry without another write', async () => {
  const confirmation = createReviewConfirmation();
  let writes = 0, reads = 0;
  const commit = async () => { writes++; };
  const answer = async () => { if (++reads === 1) throw new Error('429 Too Many Requests'); return 'Chennai'; };
  await assert.rejects(confirmation.run(commit, answer));
  assert.equal(confirmation.isSaved(), true);
  assert.equal(await confirmation.run(commit, answer), 'Chennai');
  assert.equal(writes, 1);
});

test('failed confirmation must be saved before requesting an answer', async () => {
  const confirmation = createReviewConfirmation();
  let reads = 0;
  await assert.rejects(confirmation.run(async () => { throw new Error('Save failed'); }, async () => { reads++; }));
  assert.equal(confirmation.isSaved(), false);
  assert.equal(reads, 0);
});
