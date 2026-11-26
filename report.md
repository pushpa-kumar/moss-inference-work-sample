# Moss Inference: work sample

Repo: https://github.com/pushpa-kumar/moss-inference-work-sample

## Ideas on how Moss works

Right now, for a cloud-synced index, the local copy does not get the updated copy unless we poll or load the index again. Maybe we can create a publish-subscribe method, where the cloud server sends a notification that the index is updated. This way we would have the updated data all the time. This may not be an issue, because documents may not change that frequently, but it would be a good addition.

Another thought is that the whole index is stored locally. What if the index cannot fit on the device because of memory? We could have a hierarchical retrieval, inspired by computer caches, where we retrieve only part of the index. The first query may take time, but later ones would be faster (maybe a semantic cache, just an idea, I am not sure if it is feasible). This would be useful for large documentation, or a single machine handling multiple indexes. It would add a bit of latency, so it could be optional for large documents.

## 1. Portal

**What I liked**

I liked that I can test retrieval in the Playground without writing code. I pick a model and an index and ask a question. It also shows the retrieval time, first token time and total time for each message.

I asked "how to setup okta sso" using moss/fastlane-1, with and without the agent-memory-context index. With the index, I got a short answer from the docs in 727 ms. Without it, I got a long, generic Okta guide in 9,242 ms. First token time was about the same. The answer was shorter because of the context, so this is really a win for retrieval. But the Playground made it easy to see.

**What I didn't like**

Some customers may not know what an index is, and setting one up can feel overwhelming. Maybe we should create a simple interface where customers can just upload docs and test the model directly.

**What I would improve**

Moss advertises sub-10 ms retrieval for voice agents, but I couldn't test a voice agent on my own docs in the portal. The Playground is text only, and the Founding Agent only builds from a website. There is an integration guide (https://www.moss.dev/integrations/livekit), but it needs code.

I would add a simple flow: upload docs, and talk to a voice agent on them with moss/fastlane-1. It would show the latency, next to a typical setup, so customers can see the difference themselves. We may also give an interface where they can deploy the agent directly from the portal, which might be more convenient.

## 2. Inference API

**What I liked**

I liked that private documents, like confidential and personal ones, can be kept in an index stored only on our device, and we can use that as context.

**What I didn't like**

Honestly, I couldn't find anything I disliked here. I cannot see the internal implementation, so I cannot comment on it.

**What I would improve**

If customers want it, we can colocate the LLM and the index, for example by running a small model locally. This would make retrieval faster and reduce network hops.

The things I said for the portal can also be extended here.

## 3. Tasks API

**What I tested**

I ran two tasks with known answers: finding the cheapest Travel book on books.toscrape.com, and finding the Telugu film whose song won the Oscar (RRR, Naatu Naatu) on Wikipedia. I ran them with GLM 5.3 (the portal default) and with moss-balanced plus an output schema. With moss-balanced, I also ran each task with and without a start URL.

**What I liked**

I liked that I can see the walkthrough of the website in the portal. It shows a recording with screenshots of each step, so I can see exactly what the agent did.

With and without a start URL, the agent still found the right pages and got every field correct. Without a URL it took about one extra step. For the movie task, it searched DuckDuckGo and then went to Wikipedia.

**What I didn't like**

The latency is too high, and sometimes it breaks. A simple lookup across 2-3 pages took about 30-40 seconds. I would like to improve both of these.

**Where I broke it**

With GLM 5.3 and no schema, 2 of 3 runs failed with "no answer". In one of them, the agent had the correct answer and saved it in a file, but the task was still marked as failed. In both failures, the run ended right after a tool call, without a final reply.

When I gave GLM 5.3 a similar situation directly through the Inference API, it answered correctly 30 out of 30 times. So the problem seems to be in how the task runner handles the last step, not in the model.

**Results**

- moss-balanced with a schema: 6 of 6 tasks completed, all fields correct, about 30-40 seconds and $0.07 each.
- GLM 5.3 without a schema: 1 of 3 completed, about 20-40 seconds and $0.025 each.
