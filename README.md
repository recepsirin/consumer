# API CONSUMER

## Context

This documentation addresses the management of a cluster comprising three nodes, each hosting identical APIs.
The cluster is susceptible to instability, potentially resulting in failures. Ensuring consistent application of actions across all nodes is crucial,
particularly concerning POST and DELETE requests. In the event of a failure in any node, it is imperative to rollback actions across all nodes to apply system integrity,
aiming for the most reliable request handling possible.

### So, How Can We Deal With It?


Before delving into solutions and approaches, I'd like to briefly mention what transaction and rollback mean in databases.

### Understanding Commit and Rollback in Databases

- **Commit**: A commit operation finalizes a transaction by saving all changes made within that transaction to the database. Once committed, these changes become permanent and cannot be undone through normal means unless a backup or log is restored.

- **Rollback**: Conversely, a rollback undoes all changes made in a transaction, returning the database to its state before the transaction began. This is useful for recovering from errors or inconsistencies within a transaction.


But, we don't have them in the context of HTTP requests and RESTful services, by the protocol's design!
So, the concepts of "commit" and "rollback" as understood in databases and transactions do not directly apply. HTTP requests are stateless, meaning each request is independent and does not inherently carry forward the state of previous requests. Therefore, the mechanisms for managing transactions and their outcomes differ significantly from those in database management systems.

And, we boil it all down, we have alternative approaches and strategies!!


#### Strategies for Managing Transactions in HTTP Services

1. **Eventual Consistency and Retries**: One approach is to design services to achieve eventual consistency, where temporary inconsistencies are resolved over time through retries or compensating actions. This avoids the need for explicit commit or rollback mechanisms.

2. **Compensation Transactions**: Another strategy involves using compensating transactions. If a part of a transaction fails, a compensating action is taken to reverse the effects of the partially completed transaction. This requires careful design to ensure that compensations correctly restore the system to its intended state.

3. **State Management**: While RESTful services aim to be stateless, managing state across multiple services can sometimes necessitate tracking changes and applying compensations. This often involves external state management solutions or databases that track the progress of transactions across services.

4. **Retry Logic**: Implementing retry logic in clients or services can help mitigate transient failures. This doesn't roll back a transaction but allows for repeated attempts until success, which can be effective in environments where temporary issues are common.

5. **Circuit Breaker Pattern**: To prevent cascading failures, the circuit breaker pattern can be used. It detects failures and prevents further requests to a failing service, allowing it to recover before resuming normal operation.

These approaches and strategies are generally used in API gateways and distributed transaction management. Since we know our API logic and I am personally a bit familiar with Saga execution coordinator, I would like to go for compensation transactions instead circuit break.
I mean the circuit breaker pattern is focused on preventing cascading failures by temporarily suspending requests to failing services while compensation transactions are focused on maintaining data consistency in distributed transactions by executing compensating actions when part of the transaction fails. Both patterns are essential tools in the toolbox of distributed system architects and are often used in conjunction to build resilient and reliable systems.
Yes, as we can understand both of them surely have trade-offs, but when it comes to flexibility and partial failure handling, by allowing partial failures and without needing to rollback entire transaction gets my biased perception comparatively to reduced latency that comes with circuit breaker!
