import { main } from './runtime-errors';

main().catch(() => {
  process.stderr.write('Native Langfuse collection failed; coverage incomplete.\n');
  process.exitCode = 1;
});
