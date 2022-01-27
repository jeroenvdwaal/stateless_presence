# CQRS variant 2 prototype

import cmd
from pprint import pprint
import string
import asyncio
from dotmap import DotMap



class EventStore:
    # Simple observer model represents the event store.
    def __init__(self) -> None:
        self.store = []
        self.subscribers = []

    def addSubscriber(self, subscriber):
        self.subscribers.append(subscriber)

    def postEvent(self, data):
        self.store.append(data)
        for subscriber in self.subscribers:
            subscriber.update(data)

class SubscriberReadModel:
    # Read only model build from EventStore events
    def __init__(self) -> None:
        self.model = dict()

    def update(self, event):
        # Add empty set if tenant is not known
        if event.tenantId not in self.model:
            self.model[event.tenantId] = []

        if event.operation == 'add':
            if event.sipUri not in self.model[event.tenantId]:
                self.model[event.tenantId].append(event.sipUri)    
                pprint(f'Model updated: {self.model}')

class CommandProcessor:
    def __init__(self, cmdQueue: asyncio.Queue, eventStore: EventStore) -> None:
        self.cmdQueue = cmdQueue
        self.eventStore = eventStore

    def start(self):
        return asyncio.create_task(self.__task())

    async def __task(self):
        print('Command processing started')
        try:
            while True:
                cmd = await self.cmdQueue.get()
                print(f'Command received, data: {cmd}')
                self.eventStore.postEvent(cmd)
        except asyncio.CancelledError:
            print('Command processing task graceful ended')


class API:

    def __init__(self, cmdQueue: asyncio.Queue) -> None:
        self.cmdQueue = cmdQueue

    # Post the operations of the API as commands in the queue
    # Processing will take place down the pipeline.
    async def AddPresenceSubscription(self, tenantId: string, sipUri: string):
        cmd = DotMap({'operation': 'add', 'tenantId': tenantId, 'sipUri': sipUri})
        await self.cmdQueue.put(cmd)

    async def RemovePresenceSubscription(self, tenantId: string, sipUri: string):
        cmd = DotMap({'operation': 'remove', 'tenantId': tenantId, 'sipUri': sipUri})
        await self.cmdQueue.put(cmd)


class PresenceDemo:
    def __init__(self) -> None:
        self.cmdQueue = asyncio.Queue()
        self.API = API(self.cmdQueue)
        self.eventStore = EventStore()
        self.cmdProcessor = CommandProcessor(self.cmdQueue, self.eventStore)
        
        # ReadModels
        self.subscriberReadModel = SubscriberReadModel()
        self.eventStore.addSubscriber(self.subscriberReadModel)


async def main():
    pd = PresenceDemo()
    cmdProcessorTask = pd.cmdProcessor.start()
    await asyncio.sleep(1)
    await pd.API.AddPresenceSubscription('tenant_a', 'sip:agent@nu.nl')
    await asyncio.sleep(2)
    cmdProcessorTask.cancel()
    await cmdProcessorTask

asyncio.run(main())
