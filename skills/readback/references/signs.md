# Signs

What makes code hard for a person to read, and what to do about each. Go through every group and write down each sign you find, one line each with `file:line`.

Each line pairs a sign with its fix. A fix marked **report** changes what the code does, so it is never applied during a run. Write it in the report and leave the code as it is.

Unreadable code fails in two opposite ways. Some of it is too much: more code than the job needs. Some of it is too packed: the right amount of code, pressed together so tightly that nobody can follow it. The first gets shorter when fixed and the second gets longer. Neither length is the goal.

The groups are in the order the passes run.

## Too much

Code that would not be missed.

- A function, class, export or file that nothing calls → delete it, once it is proven unreachable (see the note under this list)
- A parameter, field or variable that is never read → delete it
- A wrapper that only passes its arguments on to one other function → call that function directly
- An interface with one implementation, or a factory that builds one type → use the type itself
- An option, flag or config key that only ever has one value → put the value in the code
- A check for something that cannot happen here, like a null test on a value built two lines above → delete the check
- The same check repeated at every layer on the way down → keep it once, where untrusted data enters
- A helper that rebuilds what the language or a library already in the project provides → use the built-in
- Two or more blocks that differ by one value → one function that takes the value
- A file kept next to its replacement, like `parser_v2` beside `parser`, `utils_new` or `final` → one file, once the callers of the old one are moved
- A layer that only converts one shape into an identical shape → remove the layer

Unreachable means proven. A search for the name is not proof. Check reflection, dependency injection by name, routes, config files, scheduled jobs, templates, string lookups and callers outside the repo. Anything that cannot be proven is **report**.

## Too packed

Code that is the right size and still cannot be followed.

- A script or function that runs top to bottom for a hundred lines with no named steps → a short main that names each step, with the steps below it
- A pipeline or call chain of five or more stages on one line → one stage per line, with a reason above any stage whose purpose is not plain
- A condition with three or more parts joined by and and or → name the parts, or split it into two plain checks
- A ternary inside a ternary → an if, or a function with a name
- Several assignments or statements on one line → one per line
- A regular expression, format string or bit operation with nothing to say what it matches or produces → a name that says it, or one line above it with an example input and output
- Text built by hand with escaped quotes, like JSON or SQL assembled piece by piece → a template whose shape is visible, producing the same bytes
- Lists that only make sense together, read by the same index → one list of records, where the language has records
- A file whose header comment lists the steps because the code does not show them → make the code show them, then shorten the comment

## Names

- A name that says nothing about the use, like `data`, `result`, `temp`, `obj`, `item`, `info`, `handle`, `process` or `manager` → a name that says what it holds or does in this program
- A single letter outside a short loop → a word
- A name that states the type and not the meaning, like `userList` or `strName` → the meaning, like `invitedUsers`
- One thing called by different names in different places → one name everywhere
- Different things sharing one name → a name each
- A name that no longer matches what the code does, like `getUser` that also writes → rename it to what it does. Splitting it is a change of behavior only if callers can tell, so check first
- A boolean whose name does not read as true or false, like `flag` or `status` → a question, like `isLocked`
- A name with `and` in it → two functions
- A number or string whose meaning is not on the page, like `86400` or `"TCR"` → a named constant

Names that other code outside the module depends on are part of the public surface. Leave them and **report**.

## Shape

- A function that does several jobs in a row → one function per job, called in order from a function that reads as the list of jobs
- A function whose first half and second half share no variables → two functions
- Definitions and the code that runs mixed together down a file → definitions first, the run last, or the other way round, but not interleaved
- A function with more than four parameters, or one that takes booleans to switch its behavior → a record for the parameters, or one function per behavior
- Related code spread across files that always change together → next to each other
- Unrelated code in one file because it was written in one sitting → a file each
- A helper used once, far from its only caller → next to the caller, or inline if that reads better
- State changed from many places with no single owner → one place that changes it

## Flow

- Nesting more than three levels deep → return early for the cases that end the function, so the main path stays at the left edge
- An else after a branch that already returned → drop the else
- A loop that filters, transforms and collects by hand → the language's own filter and map, when the result reads more plainly
- A chain of filter and map so long that the steps cannot be told apart → named steps, or a plain loop
- A flag set in one place and tested far below to decide what to do → do it where the decision is made
- A switch or if chain that picks behavior by a type name or a string → a lookup table, or one type per behavior
- A negative condition followed by the long branch → put the short case first
- A value changed again and again under one name through a function → a new name for each meaning

## Errors

Most fixes in this group change what callers see, so most are **report**.

- A catch that does nothing, or only logs, and carries on → **report**. The lock pins the swallowing as current behavior
- A catch of every error where one kind is expected → **report**
- An error replaced by a default value, so a failure looks like a real answer → **report**
- A retry, a sleep or a timeout with no stated reason → **report**, and ask what it works around
- A failure that is hidden by how a statement is written, like a failed command inside an `export` → **report**. This is a bug to pin, not to fix
- The same try and catch written around every call → one place that handles the error, only if what callers see stays the same
- An error message that does not say what was being done or with which value → **report** if anything reads the message, otherwise add the missing part

## Comments

Run this last. Good names remove most comments on their own.

- A comment that says what the next line plainly says → delete it
- A comment that explains a name → fix the name and delete the comment
- A banner or divider that marks a section → a function with a name
- Code that is commented out → delete it. The history has it
- A comment that no longer matches the code → make it true, or delete it if the code now says it
- A doc block on every function that repeats the signature → keep only what the signature cannot say
- A note about the conversation that produced the code, like "as requested" or "fixed per review" → delete it
- A comment about something outside the code, like a limit of another system, a reason for a workaround or a rule from the business → keep it, word for word if in doubt

## Special cases

Write these down and count them. Each one is code for a single situation that the design did not account for. They are not fixed one by one. The count before and after is a measure of the run.

- An if for one value, one customer, one environment or one date
- A parameter that only one caller sets
- A swallowed error
- A retry or a sleep
- A test that is skipped or disabled
- A type check that is forced past, like a cast, an `any` or a suppressed warning

Before fixing signs one at a time, look at the whole list for one change that removes several of them at once. A missing concept in the code often shows up as five separate signs.

## Leave alone

These look like signs and are not. Changing them is how a cleanup breaks working code.

- A check at the edge of the system, where input from users, files or the network arrives
- Code that is hard to read because it is fast, with a measurement or a comment that says so
- An odd-looking line with a comment naming the bug or the outside system it works around
- A name, a route, a column, a message or a file format that something outside the module reads
- The order of side effects, like writes, calls and logs, even where another order would read better
- Generated code and vendored code
- Tests, once the lock is accepted
- Code that already reads well. If the audit finds little, say so and stop
