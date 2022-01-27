# Presence service

Project to investigate how to create a stateless approach for a load balancing Presence Service.

Presence registration and de-registration could be done from within a `REST API`, which allows a load balancer to forward to any of the running services. This allows for easy scaling up and scaling down. The response of the service is only returned in case the service has successfully processed the API call. If not processed in a particular time-span, the request can be send to another service. 

- **Problem 1.** Interesting to see what happens here, if timeout occurs and Service A and Service B are both handling the same call. Some mechanism should be in there to keep things sane. Eventually consistent?
- **Problem 2.** In case we do round robin, we could have a registration and de-registration for the same agent happening in two different services. This can become time critical.

- **Problem 3.** Presence updates are a kind of processes, which do need a thread/process. Events can be posted on a bus, or Kafka, whatever. How are the presence jobs divided over all running services? What if a service crashes, or we change the number of instances due to scaling up or down.

Possible ideas: all service instances share a redis cache, in which the presence subscription administration is held. Accessed by it's tenant ID. Using transactions to keep the administration sane.

Thought. The idea is not to have state in the service. The work needs to be partitioned along the number of instances. This requires some 'management' kind of task. The management could be a service on it's own, or is a part of the Presence Service.

Every service is just reading it's assigned presence tasks, and execute these and put the results on the event bus. 
**Question** Do we like a callback or an eventing system? Eventing allows for other service to recover from failure, by replaying events.

Other thought. Build the whole in a `CQRS` pattern. Incoming requests are in a command queue. Fetched by one of the running instances. Executes and send events as a result. The events are used to build a model of the subscriptions, which is used by the Services to fetch Teams presence.

Important, try to prevent the need for context or call it a session.


## CQRS approach

See drawing. An alternative to the drawing.

Use command queue, to add or remove agent registration for presence. Create read models from these operations. We now need to fetch the actual presence from Teams. Instead of doing this by a separate process, the actual fetch is turned into a command, which is enqueued in the command queue. These events are processed by an entities, which is doing the actual Teams Graph API call. The result are again events, which are processed to a read model with the latest presence and possibly forwarded to an event bus. 

Restart of the module, is re-reading the events, which brings the read model for presence and the subscriptions back to what it was.

