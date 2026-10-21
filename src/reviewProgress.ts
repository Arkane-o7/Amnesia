type Receipt = { event_id: string; session_id: string };
type Request = { workspace_id: string; session_id: string; text: string; request_id: string; new_session: boolean };
type Send = (path: string, body: Request) => Promise<Receipt>;

// Answer generation may fail after a confirmation has already been saved.
export function createReviewConfirmation() {
  let saved = false;
  return {
    isSaved: () => saved,
    async run<T>(commit: () => Promise<unknown>, readAnswer: () => Promise<T>): Promise<T> {
      if (!saved) { await commit(); saved = true; }
      return readAnswer();
    },
  };
}

// A stable request survives failed/lost responses. The server owns deduplication.
export function createReviewWriter(send: Send) {
  const steps = new Map<number, { body: Request; result?: Receipt }>();
  return {
    isCommitted(step: number) { return Boolean(steps.get(step)?.result); },
    async write(step: number, workspaceId: string, sessionId: string, text: string) {
      let pending = steps.get(step);
      if (pending?.result) return pending.result;
      if (!pending || pending.body.text !== text || pending.body.workspace_id !== workspaceId) {
        pending = { body: { workspace_id: workspaceId, session_id: sessionId, text,
          request_id: crypto.randomUUID(), new_session: step > 1 } };
        steps.set(step, pending);
      }
      pending.result = await send('events', pending.body);
      return pending.result;
    },
  };
}
