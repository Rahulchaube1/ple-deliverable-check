# Testing a deliverable-checking engineering agent on GPT-OSS 120B

Development results as of November 25, 2026. Three of the 29 PLE development tasks have a measured result for this harness.

The harness asks the model to identify its deliverables, write them inside the task workspace, then reopen the files before declaring completion. We tested whether that process could finish with GPT-OSS 120B on Groq’s free service. All three trials exported a file and received zero reward. A daily token limit interrupted two trials, and a per-minute limit interrupted the third.

| Development task | Official reward | Elapsed time | Input tokens | Output tokens | Exported bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| [Data-hall MEP routing](./evaluation-results/45348246811.json) | 0.0 | 19m 49s | 112,022 | 58,840 | 10,397 |
| [Data-center site model](./evaluation-results/45370409654.json) | 0.0 | 3m 19s | 19,449 | 4,705 | 1,694 |
| [Offset data-hall MEP routing](./evaluation-results/45598717259.json) | 0.0 | 1m 47s | 7,175 | 4,953 | 14,079 |

The official runner classified all three outcomes as harness failures. All three tasks use automated checks. The artifact checker counted one usable task in each of the first two single-task exports. That count establishes that the output could be collected. None of the runs yielded a positive score or established that the exported design met the engineering requirements. Coverage is 3/29, so a full development-set average is still pending.

The site-model trial illustrates a practical limit of the preflight test. Groq answered a short request before the trial, then rejected a 5,527-token request when the organization had 177 daily tokens left. A successful preflight showed that the model was reachable, but it did not establish that enough daily quota remained to finish an assignment.

All three runs used the [same harness revision](https://github.com/Rahulchaube1/ple-deliverable-check/tree/42ac6a6ad624dd77205657fe696bba5fe8a772a0) and [competition kit revision](https://github.com/google-research/ple/tree/5cf736f8b6e6f28eea71cae52de0c3bedaa88fa2). The linked task records identify the GitHub Actions runs, encrypted evidence artifacts and provider quota observations. No substitute model judge was used in these three trials.
