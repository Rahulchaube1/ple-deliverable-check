# Testing a deliverable-checking engineering agent on GPT-OSS 120B

Development results as of November 24, 2026. Two of the 29 PLE development tasks have a measured result for this harness.

The harness asks the model to identify its deliverables, write them inside the task workspace, then reopen the files before declaring completion. We tested whether that process could finish with GPT-OSS 120B on Groq’s free service. Both trials exported a file and received zero reward after a daily token limit interrupted the agent.

| Development task | Official reward | Elapsed time | Input tokens | Output tokens | Exported bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| [Data-hall MEP routing](./evaluation-results/45348246811.json) | 0.0 | 19m 49s | 112,022 | 58,840 | 10,397 |
| [Data-center site model](./evaluation-results/45370409654.json) | 0.0 | 3m 19s | 19,449 | 4,705 | 1,694 |

The official runner classified both outcomes as harness failures. Both tasks use automated checks. The artifact checker counted one usable task in each single-task export. That count establishes that the output could be collected. Neither run yielded a positive score or established that the exported design met the engineering requirements. Coverage is 2/29, so a full development-set average is still pending.

The site-model trial illustrates a practical limit of the preflight test. Groq answered a short request before the trial, then rejected a 5,527-token request when the organization had 177 daily tokens left. A successful preflight showed that the model was reachable, but it did not establish that enough daily quota remained to finish an assignment.

Both runs used the [same harness revision](https://github.com/Rahulchaube1/ple-deliverable-check/tree/42ac6a6ad624dd77205657fe696bba5fe8a772a0) and [competition kit revision](https://github.com/google-research/ple/tree/5cf736f8b6e6f28eea71cae52de0c3bedaa88fa2). The linked task records identify the GitHub Actions runs, encrypted evidence artifacts and provider quota observations. No substitute model judge was used in these two trials.
