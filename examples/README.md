# Examples

Three small modules written badly on purpose. Each one works, and each one is hard to read in a different way. They are what the skill is tested against.

| Example | Hard to read because | Run it |
| --- | --- | --- |
| [typescript-order-pricing](typescript-order-pricing) | Too much code for the job | `node typescript-order-pricing/demo.ts` |
| [java-csv-import](java-csv-import) | One long, deeply nested method with names that say nothing | compile `src/main/java` and run `com.example.csvimport.Demo` |
| [shell-publish-build](shell-publish-build) | The right amount of code, packed too tightly | needs a deploy service, or a stub for `curl` |

## Answer keys

Each example has an `answer-key.json`. Every entry names a file, a piece of text found on exactly one line of it, the group from [the signs catalog](../skills/readback/references/signs.md), and what a run should do there:

- `fix`: change it
- `report`: write it in the report and leave the code as it is, because the fix would change behavior
- `count`: a special case, counted before and after
- `leave`: it looks like a sign and is not. Changing it is a failed run

Each example also carries at least one real bug. A run must pin the bug with a test and report it, never fix it.

`node evals/check-answer-keys.mjs` confirms that every entry still points at one line.
