# API Consumer


## Table of Contents

1. [Context](#context)
2. [Understanding Commit and Rollback in Databases](#understanding-commit-and-rollback-in-databases)
3. [Strategies for Managing Transactions in HTTP Services](#strategies-for-managing-transactions-in-http-services)
4. [What if all retry attempts fail](#what-if-all-retry-attempts-fail)
5. [Design Decisions](#design-decisions)
    - [APIClient Class](#apiclient-class)
    - [asyncio.gather Usage](#asynciogather-usage)
    - [TransactionCoordinator Class](#transactioncoordinator-class)
    - [TransactionState Enumeration](#transactionstate-enumeration)
    - [Retry Strategies](#retry-strategies)
    - [Coding Style](#coding-style)
6. [Build and Run](#build-and-run)
7. [Set up Minikube](#set-up-minikube)
8. [Deploy](#deploy)
9. [Setting and Running Locally via Poetry](#setting-and-running-locally)

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





## Design Decisions

### APIClient Class
- **APIClient** class is implemented to encapsulate API logic and request design, providing dedicated interfaces for managing node-specific functionality with each instance.

### asyncio.gather Usage
- **asyncio.gather** is used to concurrently make requests to each node, treating them as individual units of work, and collecting their responses or errors.

### TransactionCoordinator Class
- **TransactionCoordinator** class  is implemented to coordinate transactions across multiple nodes within the cluster, ensuring eventual consistency in the system. By orchestrating transaction execution, tracking transaction states and implementing error handling and rollback mechanisms, it maintains a consistent state across all nodes over time. Through its management of transactional operations and state tracking, the TransactionCoordinator contributes to achieving eventual consistency, where the system converges to a consistent state despite any kind of failures.

### TransactionState Enumeration
- **TransactionState** is defined to help in effectively managing and tracking the state of transactions within the coordinator, enabling error handling, retries and compensations as needed.
  - **SUCCEEDED** Indicates that the transaction was successfully completed without any issues.
  - **ROLLED_BACK** Signifies that the transaction was partially successful but had to be rolled back due to some failure or inconsistency.
  - **TO_BE_RETRIED** Implies that the transaction encountered temporary issues or failures and needs to be retried.
  - **FAILED: Indicates** that the transaction failed to complete successfully and cannot proceed further.

### Retry Strategies
- **Exponential Backoff Retry Strategy** is implemented with tenacity library that utilizes exponential backoff to retry transactions up to a maximum number of attempts, with increasing wait times between retries.


- **Conditional Retry Strategy** is implemented with again tenacity that retries transactions based on specified conditions. It retries transactions if the result is either TransactionState.TO_BE_RETRIED or TransactionState.FAILED.

### Coding Style
- **Style**
  - **black:** minimizes debates over code formatting preferences and enhances code readability.
  - **isort:** sorts and groups imports, ensuring a clean and consistent import layout.
  - **mypy** enforces static type checking, ensuring type safety and correctness of type annotations.
  - **flake8** performs static code analysis to enforce coding standards and identify potential issues or violations.
  - **pre-commit hooks** configures to automatically run code formatting, linting, and other checks before each commit, ensuring that only properly formatted and validated code is committed to version control.



## Build and Run

Build and tag the dtc image from Dockerfile
```bash
docker build -t dtc:0.1 .
```

Run the dtc container
```bash
docker run -d -p 8000:8000 dtc:0.1
```


## Set up minikube

[OPTIONAL]Download the latest Minikube binary for Linux in the current directory.
If you're using a different operating system, you'll need to download the appropriate Minikube binary for that OS. You can find the download links and instructions for various operating systems on the Minikube GitHub releases page or the official Minikube website.
```bash
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64 \\n&& sudo install minikube-linux-amd64 /usr/local/bin/minikube\n
```

Start a local Kubernetes cluster using Minikube with the Docker driver.
```bash
minikube start --driver=docker
```

Check the status of the local Kubernetes cluster managed by Minikube. You should see that it is in the RUNNING state.
```bash
minikube status
```

[OPTIONAL]Open the Kubernetes dashboard for the local cluster managed by Minikube in a web browser.
```bash
minikube dashboard
```

## Deploy

Deploy the application file defined in manifests/deployment.yaml
```bash
minikube kubectl -- apply -f manifests/deployment.yaml
```

Expected output:
```deployment.apps/dtc-app created```


Deploy the service file defined in manifests/service.yaml
```bash
minikube kubectl -- apply -f manifests/service.yaml
```

Expected output:
```service/dtc-service created```


Verify that your deployment and service are running correctly.

Deployment:
```bash
minikube kubectl get deployments
```

Expected output:
```
NAME      READY   UP-TO-DATE   AVAILABLE   AGE
dtc-app   0/3     3            0           5m58s
```

Deployment:
```bash
minikube kubectl get services
```

Expected output:
```
NAME          TYPE        CLUSTER-IP       EXTERNAL-IP   PORT(S)    AGE
dtc-service   ClusterIP   10.107.178.202   <none>        8000/TCP   2m40s
kubernetes    ClusterIP   10.96.0.1        <none>        443/TCP    22h
```

Now you need to make the pod configurations.



## Setting and Running Locally


To create a virtual environment
```bash
poetry shell
```

To install dependencies
```bash
poetry install
```

[OPTIONAL]To build the application as a package via poetry if necessary
```bash
poetry build
```

To run tests
```bash
poetry run pytest
```

#### Test Reports
To add coverage plugin
```bash
poetry add --dev pytest-cov
```

To generate test coverage report
```bash
poetry run pytest --cov
```

#### To Run

##### You can either run it as an HTTP API via
```bash
poetry run uvicorn dtc_api:app --reload
```

##### or create a Python file, then call .coordinate() and attach it to an event loop.
```bash
try:
    asyncio.run(TransactionCoordinator().coordinate(GROUPID, ACTION))
except RetryError:
    pass
```
