## Latency (no index, 5 runs, max 80 tokens; first token = first visible text, so reasoning time is included)

| model | first token median | min-max | total median | non-empty |
|---|---|---|---|---|
| moss/fastlane-1 | 88 ms | 86-177 ms | 534 ms | 5/5 |
| openai/gpt-6-luna | 1588 ms | 715-3641 ms | 1636 ms | 5/5 |
| anthropic/claude-haiku-5.5 | 655 ms | 565-892 ms | 966 ms | 5/5 |
| google/gemini-3.5-flash-lite | 913 ms | 709-1031 ms | 918 ms | 5/5 |
| z-ai/glm-5.3 | 609 ms | 534-652 ms | 1023 ms | 5/5 |

## Retrieval overhead (moss/fastlane-1, 'how to setup okta sso', 5 runs)

| index | first token median | retrieve ms median | prompt tokens | total median |
|---|---|---|---|---|
| none | 84 ms | 0 | 104 | 1231 ms |
| agent-memory-context | 153 ms | 10 | 449 | 792 ms |

## RAG (moss/fastlane-1)

| question | index | expected | found |
|---|---|---|---|
| Where do I set the default role for new teammates who join via SSO? | agent-memory-context | settings > security | yes |
| How long does a refund take after my return is received? | demo-customer_faqs | 5-7 | yes |
| Is there a fee if I return opened electronics? | demo-customer_faqs | 15% | yes |
| how to setup okta sso | demo-customer_faqs | do not have / don't have | yes |
| What is the name of your company's CEO? | demo-customer_faqs | do not have / don't have | yes |

## Compatibility

| check | result |
|---|---|
| OpenAI SDK + index header | 'Hello! How can I help you today?' |
| /responses | 200 'Hello! How can I help you today?' |
| tool calling | get_order_status({"order_id": "4471"}) |
| JSON schema output | { "intent": "refund", "order_id": "9921" } |

## Errors

| case | status | message |
|---|---|---|
| unknown model | 400 | Unknown model moss/does-not-exist. Send model moss/fastlane-1, or a vendor model name with your own key in X-M |
| index that does not exist | 403 | X-Moss-Indexes names an index outside this project |
| wrong API key | 401 | The project credentials were rejected |
| key without colon | 401 | Send Bearer project_id:project_key |
| unknown field (chat/completions) | 200 | (no error, it answered) |
| negative max_tokens | 400 | max_tokens must be at least 1, got -5. (parameter=max_tokens, value=-5) |
| unknown field (responses) | 400 | banana is not supported |
