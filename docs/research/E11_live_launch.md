# Taking the book live: sprint E11, told as a story

## An order that would have gone the wrong way

On the second evening of a paper book's life, the order code was about to buy more
of a stock it already held at its target. The book is a list of positions the
research says to hold, each one a dollar amount the model wants; the evening job
works out what to hold and the morning job turns that into orders. The name in
question had been bought on the first evening, eighty thousand dollars of it, and
its target had not moved. The order code read the target as the order, so it would
have bought another eighty thousand dollars of the same name, and it would have
done the same for every other name in the book, doubling the account on the second
day and on every day after that. Nobody had sent an order yet: the book was paper,
it proposed, it recorded what it would have done, and it never reached a broker.
The defect was found in a review of the code that places orders, before the first
real message left the building, and the fix is one idea wide: an order is a
change, not a position. The change has a name in the code, the delta, and it is
the target the evening job wants minus the position the account holds.

That incident is the reason this document exists. For ten sprints the project had
been building machinery, and every piece of it was measured against its own
numbers: an estimator against a stored loss, a signal against a pre-registered
information coefficient, a construction rule against an effective breadth. None of
those tests could see a second evening. A research result lives in one
cross-section at a time; a live book lives in a sequence of them, and the sequence
is where the integration defects live: a field a broker returns as text, a
database column that refuses a value the code writes every day, a scheduled job
that fires outside the window its venue allows, a target that is not a change.

What follows is the story of the eleventh sprint, the one that took the book from
a stored backtest to a scheduled paper-trading loop and then to the edge of a real
one. It is written for a listener with a quantitative background and no knowledge
of this project, so every term is explained where it first appears. Every number
in it is read from a file the project stores: the sprint results, the handoff log,
the run transcripts, the fixtures the live page serves, or the code and tests that
pin the rules.

## What the live book is, and what runs each evening

The book is a long and short portfolio of large American equities. A long position
profits when a stock rises and a short position profits when it falls; the two
sides are sized together so that the book makes a bet on which names will beat
which others rather than on whether the market rises. The book is a paper book:
it computes the orders it would send, records them as though they had been sent,
and reconciles them against a simulated account of one million dollars of net
asset value. That figure is fixed for the life of the exercise and comes from a
platform limit rather than from an optimization, a point that matters later. The
sizing decision the whole book rests on is the alpha, a number per name per day
that says how attractive the model thinks that name is.

Each evening a scheduled job wakes up and walks five steps in order. It extends
its own data history by fetching the evening's closing prices and appending them
to the stored panel. It refreshes the slow inputs, which are share counts, sector
labels and a daily file of holdings of a large exchange-traded fund that the
project uses as its running index-membership source. It builds the proposal: the
alpha for every name, the construction rule that turns alpha into weights, the
hedge that removes unintended exposure to market and sector, the constraint set,
the cost estimate and the volatility scale. It executes in paper and reconciles
what it did against the positions it stored the previous evening. And it notifies
its owner by email, with the run status in the subject line, failing loudly rather
than writing a partial day.

The job is scheduled by a cloud platform called Render, which runs the code on a
timetable without a machine of the owner's own. It fires at 22:30 coordinated
universal time, inside the after-hours session that runs from four to eight in New
York.

Two independent checks must pass before a proposal is priced, and they are often
confused, so the project keeps them apart. The first is the sanity gate: a check
that the closes the loop fetched for itself are consistent with the stored
series, run on two closes it fetched on its own evenings through the deployed
scheduler rather than through a replay. The second is the staleness rule: the run
stops entirely if any input is older than it is allowed to be, counted in trading
sessions against the most recent completed session, per input, because the
failure mode for a slow input is not a bad value but a fetch that stops happening.

The switch that makes the book real is a single variable called `dry_run`. While
it is true the loop does everything except place orders, which is how the machinery
is rehearsed without touching the market and without accumulating results that
would have to be thrown away. The owner flips it once, deliberately, and that day
becomes day one of a thirty-trading-day reporting window; the loop then runs on
indefinitely, because a book that stops after thirty days is a backtest with a long
memory. The stored clock carries a void first attempt: a start recorded on
2026-09-22 was cancelled before it counted, because the loop ran against a frozen
close and would have produced thirty identical proposals. The live page says
plainly that the clock has not started.

## Why the seed went into an object store and the new days into a database

The first integration problem was the disk. Render builds a fresh container for
every deploy and a scheduled job runs in one, so anything the loop writes is gone
by the next evening. That is fatal for this design, because the design extends its
own data history: an evening appends a session, refits the model and rehashes a
manifest that records what the run was scored on. The project solved the first half
of the problem by copying the whole artifact tree into the run's own directory
before doing anything, so a run never writes into the repository's tree; that copy
is 876 megabytes and takes about 2.4 seconds. Then it split history from the
present. The frozen history, everything through the last session any research build
wrote, lives in a private object store on Cloudflare's R2 service, in a bucket
named for the seed. The new days, which grow by one session every evening, live in
a Postgres database.

Two rules make the seed safe to depend on. The manifest is measured rather than
listed: the loader wraps the file-reading functions the run uses and records
which files it actually opened inside the data directory, so the manifest is
evidence of what a real evening reads rather than a hand-kept list that can
drift, and a downloaded file whose size or hash differs refuses the run before it
starts. And the write path is structural: one script is the only writer into the
bucket, and it refuses to run on Render, so no code path inside the deployed job
can write into frozen history.

Database access was the second decision, and the interesting part is which
protocol was refused. A shared database project serves two ways: through a
REST interface that exposes a fixed list of schemas, or through a direct
connection. The REST interface would have needed the new schema added to the
project's exposed list, a dashboard setting on a project shared with another
application, which would have widened that project's public surface; the direct
connection reaches any schema without one. The decision came with an escape
hatch: if the schema ever needs a shared-role grant, a dashboard change, or
touches the other application's data, the work stops and the owner moves the
database rather than working around it. One caveat is recorded with it: on a shared
project, schema separation is a naming discipline rather than a permission
boundary, since one role can see both schemas.

Then came first contact, and it produced four defects of the kind no unit test
finds, because each one is a disagreement between two systems that were both
internally consistent.

The first was a data type. The run records its own status as a block of key and
value pairs, stored in the database's JSON column type. Python's JSON writer
happily writes the bare token `NaN` for a value that is not a number, and the JSON
standard does not allow it; Postgres refuses it. So a column that the code wrote
every evening would have been rejected by the database on the first live run, in a
path that had only ever been exercised against a local file store. The fix
sanitizes every value on the way out, and a test asserts that a status block
containing an absent number round-trips through the database.

The second was a permission. The deploy configuration carried a service key for
the shared project, and the service key is the one that bypasses row-level
security: the rules a database uses to make one application's rows invisible to
another. Putting that key on a public web service, which is where the deploy
steps pointed, would have handed the whole shared project to anything that
compromised the service. The project stopped the deploy rather than editing the
steps, recorded the finding, and resolved it by keeping the database connection
server-side only. This is the single most useful thing the review found, and it
was found by reading a configuration file rather than by running code.

The third was the first-run marker. A fresh database has no rows, so the first
evening must be allowed to seed its appendix tables, and every evening after that
must be prevented from re-seeding them, because re-seeding would silently reset
the record of what the loop had intended to hold. The project refuses to infer
which case it is from the store being empty, because a connection check the owner
may run on any evening leaves both an empty store and a store holding a row of its
own. So
there is an explicit flag, parsed strictly, where only the exact value `true`
means first run and any other spelling is an error naming the value, and a marker
table recording the close the seed was taken through. Four states are decided in
a fixed order and only one of them seeds, and the fourth is the one worth naming:
a store whose appendix is missing while the marker is present is treated as lost
data whatever the flag says, because that is a damaged store rather than a
reminder.

The last first-contact defect was a delay rather than a crash, and it is the kind
that would have stopped every evening for a week before anyone understood it. The
index-membership file the run fetches is published by its provider with a lag: on
a normal evening it describes the membership of a session that has already
closed, which is one session behind the close being priced. The staleness rule
allowed no slack for any input, so the gate stopped the run on the universe on
every single evening. The fix is a per-input allowance, where the universe gets
one session and every other input gets none: an index snapshot is filed after the
close it describes, so one session of lag is the input behaving normally rather
than the input going stale. The run's transcript prints the allowance beside the
measurement, so a reader can see the gate passing because of it.

## The construction problem on a million dollars

The construction rule turns alpha into weights, and the live loop inherits it from
the eighth sprint, which chose a proportional rule hedged with the model's own
factor-mimicking portfolios. The live question is different in kind: not which
rule, but what to do about a small account. A million dollars spread over five
hundred names is two thousand dollars a name, which is about ten shares of a two
hundred dollar stock. Shares trade in whole units, so each position has to be
rounded to a whole share: ten shares of a two hundred dollar stock has a rounding
error of up to ten percent of the position, and a book made of such positions
carries a rounding error of about five and a half percent of its gross. That is
not a rounding error in any useful sense of the phrase; it is a systematic
difference between the book that was priced and the book that would be held.

Three answers were on the table. Raise the paper account to ten million dollars,
which cuts the rounding error roughly tenfold and preserves the five hundred name
breadth the research measured. Cut the number of names to a hundred and fifty or
so, which fixes the error and gives up breadth. Or keep a million dollars and the
full breadth, record the error as a standing limitation, and have the attribution
sprint measure the executed book rather than the target book. The first option
looked best until the account's own funding field turned out to be capped at
exactly one million dollars, which closed it by platform limit rather than by
argument.

That left the minimum position, which is the same idea as the name count seen from
the other side. Instead of holding five hundred names at two thousand dollars
each, hold fewer names at a size where rounding is small. A five thousand dollar
minimum is twenty-five shares of a two hundred dollar stock, where half a share of
error is two percent of the position and a whole share is four. It also caps the
name count by arithmetic, since a million dollars of gross admits at most two
hundred names at five thousand dollars each. So the floor was written out and
tested, and at five thousand dollars it kept twenty-seven names out of four
hundred and ninety-nine, with a gross of about 0.27 of the account, which is very
far from a diversified book.

That measurement turned a contingency into the decision, and it also brought in a
constraint nobody had been looking at. The risk model estimates about eighteen
columns a day: seven style descriptors such as size and momentum, eleven sector
factors and a market term. A book held on twenty-seven names cannot hedge eighteen
independent directions, because twenty-seven correlated names do not span eighteen
dimensions; there are nine degrees of freedom left, and the exact hedge is close to
rank deficient. The practical floor on the number of names is therefore a healthy
multiple of the number of model columns, and that constraint is harder than the
rounding arithmetic.

What the owner asked for next is the most characteristic artifact of this project:
not a guess, but a decision surface. The construction table was built as a set of
rows on one close, where each row is a rule rather than a number: dollar floors from
fifteen hundred to five thousand, top-N-by-alpha at a hundred and fifty and at two
hundred names, a two-part floor combining dollars and shares, a share floor alone,
and the full reference book of four hundred and ninety-nine names as a benchmark. Each row
drops names, re-runs the sizing on the subset that survives, re-normalizes the
subset to a gross of one, re-runs the hedge on that subset rather than reusing the
hedge built for the full book, and then quantizes to whole shares. Each row reports
its breadth as an effective name count rather than a name count, its largest
position, its realized market exposure, the total rounding error as a share of the
account, the ninetieth percentile of per-name rounding error, the post-hedge
exposure and the idiosyncratic share of variance, and both breadth bounds. Nothing
executes in that file and nothing chooses.

The owner then chose, and the reasoning is worth repeating because it is a
statement about what the project is for. The chosen row is a share-only floor: a
minimum of twenty whole shares per name and no dollar floor at all. At the fixed
point that rule kept a hundred and eighty-eight names with an effective breadth of
85.69, a governing breadth ratio of 1.355, a total rounding error of 1.25 percent
and a ninetieth percentile of 3.44 percent. The roughly fourteen percent cost in
information ratio against the fifteen hundred dollar floor is, in the owner's
words, notional, because this is a documented null book whose expected verdict is
luck; the reduction in the difference between the priced book and the held book is
real, and that difference is exactly what becomes attribution bias in the next
sprint. Share-only rather than a two-part floor, because the fifteen hundred dollar
leg costs 2.6 of effective breadth for 0.19 of a point of error, and one floor is
simpler to state than two. A hundred and eighty-eight names against eighteen model
columns leaves comfortable rank margin, which is what killed the small-N rows.

Two things about that decision are worth naming because they are discipline rather
than preference. The first is a pre-registered re-decide trigger written before the
floor was enforced: the chosen row would be compared against an enforced two
thousand dollar floor, and the choice would go back to the owner if the chosen row
lost either its lower total error or its lower ninetieth percentile, or if any
enforced row dominated it on both breadth and total error. A fall in breadth alone
would not stop the work; it would be reported and the owner could re-decide. A
trigger written before the numbers exist is what keeps a later reading of the same
numbers honest. The second is that the floor is checked on the weights that trade:
an earlier version checked the floor on the weights that were sized, before the
hedge and the re-normalization that rescale every position, and re-sizing moved
roughly one name in ten below the floor. The rule now iterates on the final
weights, dropping names below the floor and admitting names back in an order
defined by their weight relative to the floor until a full pass changes nothing.
That loop is the one the live path runs, and it is why the chosen row holds
the names it holds.

Concentration came last, and it is the one construction problem that is about risk
rather than about arithmetic. A single name's share of the book's predicted
specific variance, which is the part of the risk no factor hedge removes, can reach
levels nobody would choose. In the live book one position
carried more than half of that variance, because a name whose price had moved
by 176.97 percent in one session had a modelled specific volatility of 18.45
percent a day, or 293 percent annualized, which is a real move
rather than a bad print. The owner's rule caps any one name's share of the
predicted specific variance at ten percent, applied before the hedge and solved
directly rather than iterated: rescaling one violator at a time re-violates the
names just clamped, and a hundred passes was still moving. On the close where the rule was set, the largest share fell from
50.01 percent to exactly 10.00 percent, and three names that had been over the cap
were clamped to it, which raised everyone else's share as water fills a basin. The
rule has a cost the project states rather than hides: a capped book looks
diversified on a position report while the risk has merely been redistributed
across the remaining names.

## The cost of a stock nobody trades, and a hedge one session stale

Two defects in the live path were found by reading a number back out of a ratio,
and both had survived every research test because both live inside integration
rather than inside mathematics.

The first was the cost model. Transaction cost is estimated from a name's average
daily dollar volume, called ADV: the number of shares traded in a day multiplied by
the price. The live cost estimate divided the trade by that volume, and one name in
the book had an average daily volume of zero, because a value the vendor had not
supplied was filled with a floor of one dollar before the division. The guard that
was supposed to protect the ratio, a maximum against a floor of one, turned a
missing measurement into the worst possible liquidity. The name contributed 37.2460
of the 39.0447 basis points of the establishment cost of the whole book, which is
95.4 percent of the total. The cause is in the arithmetic: the volume was a median
over the entire history rather than a trailing window, and for that name 2,409 of
its 4,208 sessions had zero volume, so the median was zero, while its
trailing-quarter median is 204.7 million dollars. Three changes followed: the live
cost measures the trailing sixty-three sessions rather than the full history, a zero
volume is treated as a missing value and filled from the panel's median, and the
impact term is computed on the change in the position rather than on the position
itself, because the cost of a trade is the trade. The same book's establishment cost fell from 53.7338 basis points to
15.0945, and the impact leg alone from 39.0447 to 0.4975.

The second was the hedge. The hedge is solved by algebra: given a design matrix of
factor exposures and a book of weights, the hedge that solves the normal equations
leaves the product of the design and the hedged book exactly zero, for any design
matrix and any book. That exactness is the problem. The design matrix is published
one session before the close being priced, so the hedge was neutralizing a
descriptor row from the previous session while the book it protected earned the
next session's returns, and every hedged exposure the project had ever printed
still read zero to machine precision, because zero is what the algebra guarantees.
Measured instead against the row the model actually publishes, the stale hedge left
between 1.2e-15 and 2.9e-14 of exposure on ordinary session pairs, 5.5e-03 and
4.5e-03 across a holiday when the priced set of names moves, and 1.8e-03 on the
seed hedge. The repair prefers a stored row dated the session after the book, falls
back to building one from data through the book's date, and records which of the
two it used; it was accepted against a pre-set bound with a negative control
confirming that the old path fails it. The lesson is worth more than the repair: a hedge that reports zero
exposure to its own design cannot be audited against that design.

## The reviews that found what the tests could not

Every one of the defects above has the same shape. The code was internally
consistent, the tests agreed with the code, and the disagreement was with the
world: a broker, a database, a calendar, a vendor file, a second evening.

The pre-launch reviews were structured around that observation, and they came in
four rounds: on the broker interface, on the owner's pre-launch items, on the
trading window and the data layer, and on the re-review's five remaining items.
What they found, in the order a reader would meet it:

Orders are deltas, and a leg at its target has a change of zero. The nightly order
is the difference between the evening's target and the account's holding, leg by
leg; when a leg is already at its target the change is no shares at all, and the
code recorded those legs as legs it had skipped. Every rerun of an unchanged book
would therefore have filed a full book of rows for names with nothing to do, and
named a dozen of them in the email.

Orders must carry an intent. A broker's order carries a direction and a quantity,
and it also carries a statement about what the order is meant to do to the
position: opening a new long, closing part of one, opening a short, covering one.
The distinction matters because the broker's rules differ by intent: the borrow
checks that decide whether a short is even possible apply only to the order that
opens one, not to the order that closes it. Every leg the run sends now carries its
intent, and the rehearsal prints it beside the change.

Broker fields are not Python objects. Two fields the live path reads back, the side
of an order and its status, arrive as text rather than as the enumeration the code
compares against; that works in a test that builds its own objects and fails
against a message that has been through a wire format. The fix parses the text into
the enumeration at the boundary, refuses a value it does not recognize, and a test
asserts that a string side reads back as the member the rest of the code expects.

Reversals must not cross zero in one order. If a book's target for a name is long
and the account holds it short, the naive order is the difference between the two,
which is a single order twice the size of the position and in the opposite
direction. That order is indistinguishable from a new position in the eyes of the
broker's risk checks, and it can be rejected for a reason that has nothing to do
with what the book wanted. The rule is that a reversal closes tonight and opens
tomorrow: the evening's order closes the held position, the name's effective target
for that evening becomes zero, and the next evening's ordinary logic opens the other
side, with the deferred reversal named in the email. The three-day rehearsal prints
exactly this, and its day three shows the deferred short opening on its own.

An accepted order is not a filled order. After the close, an order with the
time-in-force that queues it for the next session is accepted and stays accepted or
new until the market opens. Polling for fills inside the evening run would be a lie
about when the information exists, so a leg is complete when the broker has
accepted it and the run does not wait. Fills are reconciled the next evening from
the broker's own positions, which is also where holdings come from: the run asks the
account rather than inferring from what it sent.

Reads that must fail closed. Several values in the live path used to fall back to a
design constant when a read failed, and the fallbacks were silent in the cases
where silence is most dangerous. An account that could not be read used to be
treated as an empty account, which would have bought the whole book against an
account whose state nobody knew; it also decided whether the evening was an
establishment day, since an account that holds nothing is a book being built from
flat and an account that holds names is a book being rebalanced. The check now
answers from the account alone: an empty account establishes, a non-empty account
rebalances, and an account that could not be read is neither. The same reasoning
applies to equity, where a reported equity of zero or below is an answer about the
account rather than a failed read and sizing a million dollars of book against it
would produce orders every guard would then defend in the wrong denominator, so it
raises. And it applies to the trading window: the run refuses outside the hours its
venue allows, and since a refusal does no work and records nothing, the refusal now
sends one line of email naming the hour and the window, because otherwise the
owner's only signal that the evening had not run was the absence of the usual
message.

The checks around the broker are only as good as the broker they are tested
against, and a test double is a claim about the world that nobody checks. The
project's answer is a fake broker that is deliberately hostile: it rejects any
order that would cross zero, it rejects a sell larger than the quantity held unless
the order's intent is to open a short, and it returns the broker's own model objects
for positions and orders rather than dictionaries. Against that fake, a three-day
rehearsal runs the real evening and morning code end to end and prints every leg.
One more defect came from the full suite rather than from the rehearsal: a test
that drives the whole run at whatever hour the suite happens to run was stopped by
the new window refusal, which is the check working and the test being wrong about
the clock. That is also why the project runs the whole suite once at the end of a
round, not only the tests that touch what changed.

## The alpha that multiplied the wrong quantity

The most consequential defect of the launch was in the number the whole book rests
on, and it survived eleven sprints, three reviews and a full audit of the live
path.

The alpha is built from a contract, and the contract is a sentence: alpha equals
the information coefficient, times the name's specific volatility, times the name's
cross-sectional z-score, times a shrinkage factor. Each term is a stored quantity.
The information coefficient measures how well a signal predicted returns in the
past. The specific volatility is the part of a name's risk that the factor model
does not explain, and the model publishes it as a variance, which is volatility
squared, so the volatility is its square root. The z-score says where the name sits
in today's cross-section. The shrinkage factor pulls every alpha toward zero, which
is the honest response to a signal measured on a null result. The contract was
written in three places, in the evening job, in the research conversion that feeds
the eighth sprint, and in the construction table, and all three multiplied the
specific variance where the contract multiplies its square root.

The mistake was invisible because it cancels. The construction rule sizes each
position in proportion to alpha divided by the specific variance. Multiply the
alpha by the variance instead of its square root and the division removes the risk
term entirely, leaving the weight proportional to the z-score alone. The book was
never choosing between a name's expected return and its risk; it was choosing on
the z-score, and the most volatile names in the cross-section were therefore the
largest positions. Every test the project had written passed, for a reason worth
stating: a test that checks a sign, a ranking or a breadth measure cannot see a
monotone rescaling by a positive quantity, and multiplying by a variance is
exactly that per name.

The correction now lives in one function, and the before and after are measured on
one close in one session, with the old spelling patched back into that single
function so the comparison is controlled rather than remembered. The traded book's
effective name count rose from 94.2573 to 131.9175. Its largest single weight fell
from 0.033448 to 0.018723. Its forecast volatility, the number the risk budget is
expressed in, fell from 4.594 percent to 3.157 percent. The largest share of the
predicted specific variance in the traded book fell from 0.1395 to 0.0643, so the
ten percent cap, which used to bind and clamp the volatile names, stopped binding
on the book that trades at all, because the book no longer leans on them. The
number of names kept rose from 158 to 180, and the full book's gross is capped at
one afterwards with a volatility of 2.46 percent against a target of ten, so the
loop caps its book rather than levering it, which is what its own rule says it
should do. The cap still clamps two names on the sizing vector of the close
measured, where the old spelling clamped four.

How long it survived is part of the story. The contract was written in the seventh
and eighth sprints and the live conversion inherited it, so the defect was present
in every stored conversion from the beginning and in every live proposal ever
built. It was found in the pre-launch review round that read the three call sites
against the written contract rather than against each other, and the reason it
survived that long is the reason a sign test cannot see a rescaling: the process
asked whether the estimates were right, never whether the same quantity was meant
in all three places. The sprint that found it also
found the second-order consequence: the artifacts that stored the converted alpha
had been written before the correction, so a stored number describing the wrong book
would have outlived the code that produced it, and it was rebuilt through the one
function with the old value recorded beside the new one rather than quietly
replaced.

## Where the book stands, and what the next thirty days measure

The book the loop would propose tonight, on the last close this checkout can
rebuild, is a long and short book of one hundred and sixty-nine names with a gross
of exactly one of the account, an effective name count of 61.03, and a forecast
volatility of 0.10, which is the target rather than a coincidence: the volatility
scale is the last step of the construction. The stored proposal for the same close
records one hundred and fifty rows and a gross of 0.9685, because it was written by
an earlier rule and the record keeps what was written rather than restating it. The
establishment cost estimate is 15.0945 basis points, and the positions check states
plainly that the account holds nothing while the store holds a book of intentions,
which is what a dry run looks like from the account's side.

The gate that stands in front of the flip is an operational one, and it is not
cleared. Its single negative item is the same universe problem in a different
dress: the ongoing membership source exists and its daily archive has begun, but
the historical universe has not been reconstructed from it, so the book still
prices a frozen list. The reconstruction is not scheduled, because it is a
plan-changing event that would move every stored research number, and the owner has
said the universe stays split until it is a task of its own.

What remains before the first live evening is small and operational: two database
files have to be re-applied to the shared project so the tables and the grants the
loop needs exist there, a fresh proposal has to appear on the deployed page with
every panel populated from stored data, and then the owner flips a single variable.
The last of those is the project's own rule, written after an earlier start was
voided: a page that has never displayed a real proposal is not confirmed as
working.

The twenty-ninth day after the flip is what E12 measures. That
sprint's job is to explain every dollar the book made or lost, in three readings: a
holdings-based decomposition of profit into what the factors explain and what the
names did on their own, a regression of the book's returns on the factor returns as
a cross-check, and a test of skill against luck built on the standard error of a
Sharpe ratio rather than on the ratio itself. The expected verdict is written down
before the window opens, and it is luck, because the signal the book runs on is a
documented null result. All six of the project's signals failed the pre-registered
gate that decides whether a signal may size a book, so the construction machinery
was exercised on synthetic alpha with a known information coefficient. That is the design, not a disappointment: a
book whose expected verdict is luck is a clean instrument for testing whether the
machinery does what it says. If the attribution finds a factor exposure the hedge
did not neutralize, that is a defect in the machinery. If the excess return sits
inside its own standard error, the signal was null and the machinery did what it was
told.

## What this taught

The first lesson is about coverage, and it is uncomfortable. Ten sprints of
research, each with pre-registered criteria, would not have caught a single one of
the defects in this document. That is not a failure of the criteria; it is a
property of what they measure. A sprint tests an estimator against a stored loss, a
signal against a threshold written before the number existed, a construction rule
against a breadth measure. Every one of those tests holds the world still. The
defects that reached the live path all live in the seams: the broker's field read
as text instead of as an enumeration, the JSON token a database refuses, the
calendar hour a venue will not accept an order in, the target that is not a change,
the variance that is not a volatility, and the hedge that is exact against the
wrong design. None of those is a research question and none has a threshold,
because the correct behaviour is not a number but an agreement between two systems. A sprint-shaped process finds
them only by accident, which means the integration surface needs its own
instruments: rehearsals on realistic fakes, transcripts printed and read, and
configuration files read as carefully as code.

The second lesson is about tests written with the code. A test written by the
author of a function encodes the author's assumption, so it can only fail in ways
the author already imagined. The half-share rounding case, for instance, passed
because the fixture was a book that already held its targets and the code under
test never had to compute a change; the day-two case only appeared when a fake
broker remembered what it held and a rehearsal ran the real code twice. The same
shape appears in the alpha: the tests compared the converted alpha's sign and
ranking, both of which are invariant under the very error in question, and the test
that would have caught it compares the conversion against the contract's written
formula on the artifact's own inputs. The remedy is not more tests of the same kind
but tests of a different kind: negative controls that must fail, comparisons against
something outside the function, and the habit of asking what an assertion would look
like if its assumption were false.

The third lesson is why independent review earned its keep, and the mechanism is
specific. A reviewer reading a deploy configuration found the
service key that bypasses row-level security on a shared project. A reviewer
reading three call sites against a written contract found the variance where the
volatility belonged. A reviewer asking what happens when an account cannot be read
found the fallback that would have bought a book against an unknown account. None
of those is a subtle inference; all of them are invisible from inside the code,
because from inside the code the assumption is not an assumption, it is the
environment. The same argument is why the fakes have to be hostile: a test double
that answers politely will confirm anything.

The fourth lesson is about the freeze, and it is the least glamorous. The main
branch deploys: a commit on it reaches the scheduled job and the page within
minutes. So every change of behaviour before the flip waited for two clean gate
evenings, and the branch holding the next round of work stayed unmerged until its
own round of tests, lint and rehearsal had passed. The order of the last days
reflects it: the research correction that moved the book's numbers, the order
semantics, the cost correction and the review fixes all landed in batches, each
with its own tests, and the flip is the owner's single act afterward. A project
that can deploy from a commit has to decide what it is willing to deploy, and the
answer here was nothing whose consequences nobody had measured on a real evening
first. A book whose first evening is also its first test has no measurement at all.

## Where these numbers come from

Every figure in this document is read from a stored file. The evening-by-evening
record is `handoff/LOG.md`; the reports, rehearsal transcripts and review findings
are `handoff/REPORT.md`; the decisions are `handoff/PROJECT_CONTEXT.md`; the open
items are `docs/open_items.md`; the signal gate's answers are
`sprints/E7/RG_SIGNAL.json`; the sprint verdicts are the `RESULTS.json` files under
`sprints/`; the live page's data is `web/fixtures/`; and the clock is
`live/clock.json`. There is no bridge and no second copy: the two handoff documents
on this branch carry the whole record, the pre-launch review rounds and the alpha
correction included, and a test in this repository checks every number here against
those sources as they stand in the tree.
