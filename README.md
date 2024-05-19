# API CONSUMER

## Context

This documentation addresses the management of a cluster comprising three nodes, each hosting identical APIs.
The cluster is susceptible to instability, potentially resulting in failures. Ensuring consistent application of actions across all nodes is crucial,
particularly concerning POST and DELETE requests. In the event of a failure in any node, it is expected to rollback actions across all nodes to apply system integrity.
It's aimed to achieve the most reliable request handling as possible.

### So, How Can We Deal With It?


Before delving into solutions and approaches, I'd like to briefly mention what transaction and rollback mean in databases.

### Understanding Commit and Rollback in Databases

- **Commit**: A commit operation finalizes a transaction by saving all changes made within that transaction to the database. Once committed, these changes become permanent and cannot be undone through normal means unless a backup or log is restored.

- **Rollback**: Conversely, a rollback undoes all changes made in a transaction, returning the database to its state before the transaction began. This is useful for recovering from errors or inconsistencies within a transaction.


But, we don't have them in the context of HTTP requests and RESTful services, by the HTTP protocol's design!
So, the concepts of "commit" and "rollback" as understood in databases and transactions do not directly apply. HTTP requests are stateless, meaning each request is independent and does not inherently carry forward the state of previous requests. Therefore, the mechanisms for managing transactions and their outcomes differ significantly from those in database management systems.

And, when we boil it all down, we have alternative approaches and strategies!


### Strategies for Managing Transactions in HTTP Services

1. **Eventual Consistency and Retries**: One approach is to design services to achieve eventual consistency, where temporary inconsistencies are resolved over time through retries or compensating actions. This avoids the need for explicit commit or rollback mechanisms.

2. **Compensation Transactions**: Another strategy involves using compensating transactions. If a part of a transaction fails, a compensating action is taken to reverse the effects of the partially completed transaction. This requires careful design to ensure that compensations correctly restore the system to its intended state.

3. **State Management**: While RESTful services aim to be stateless, managing state across multiple services can sometimes necessitate tracking changes and applying compensations. This often involves external state management solutions or databases that track the progress of transactions across services.

4. **Retry Logic**: Implementing retry logic in clients or services can help mitigate transient failures. This doesn't roll back a transaction but allows for repeated attempts until success, which can be effective in environments where temporary issues are common.

5. **Circuit Breaker Pattern**: To prevent cascading failures, the circuit breaker pattern can be used. It detects failures and prevents further requests to a failing service, allowing it to recover before resuming normal operation.

These approaches and strategies are commonly used in API gateways and distributed transaction management. Since we have an idea over our API logic and its behavior, and my personal experience with the Saga execution coordinator, I prefer compensation transactions over the circuit breaker pattern.
The circuit breaker pattern focuses on preventing cascading failures by temporarily suspending requests to failing services. In contrast, compensation transactions prioritize maintaining data consistency in distributed transactions by executing compensating actions when part of the transaction fails.
Both patterns are essential tools in the toolkit of distributed system architects and are often used together to construct resilient and reliable systems. While both have trade-offs, I'm biased towards compensation transactions due to their flexibility and ability to handle partial failures without necessitating a rollback of the entire transaction, compared to the reduced latency offered by the circuit breaker pattern.


### What if all retry attempts fail

It's important to have a fallback mechanism in place to provide the reliability as much as possible.

Here are some potential options we can consider:

1. **Error Reporting and Logging**: Ensure that comprehensive error reporting and logging mechanisms are in place to capture details about the failed requests and retries. It can be valuable for debugging and troubleshooting purposes.

2. **Alerting and Monitoring**: Implement alerting and monitoring systems to notify relevant stakeholders about the failure. It allows for timely intervention and corrective actions to be taken.(Assume we also have an observability mechanism)

3. **Graceful Degradation**: Implement graceful degradation by disabling or scaling back non-critical features or functionality temporarily. It allows our system to continue functioning with reduced capabilities until the issue can be resolved.

4. **Automatic Rollback**: If applicable, consider implementing automatic rollback mechanisms to revert any partially completed transactions or operations to maintain data integrity and consistency.

5. **Retry with Exponential Backoff**: Adjust the retry strategy to incorporate exponential backoff, where the time between retry attempts increases exponentially with each retry. It alleviates pressure on the system and reduces the likelihood of overwhelming downstream services.

6. **Manual Intervention**: In some cases, manual intervention may be necessary to address the underlying cause of the failure.
