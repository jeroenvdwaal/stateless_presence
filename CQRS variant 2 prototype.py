# CQRS variant 2 prototype
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

class CommandQueue:
    def __init__(self) -> None:
        self.queue = asyncio.Queue()

    async def put(self, cmd):
        print(f'Command {cmd} put in CommandQueue')
        await self.queue.put(cmd)

    async def get(self):
        cmd = await self.queue.get()
        print(f'Command {cmd} fetched from CommandQueue')
        return cmd

class SubscriberReadModel:
    # Read only model build from EventStore events
    # Registers subscribers per tenant
    
    def __init__(self) -> None:
        self.model = dict()

    def update(self, event):
        # Add empty set if tenant is not known
        if event.tenantId not in self.model:
            self.model[event.tenantId] = []

        if event.operation == 'add':
            if event.sipUri not in self.model[event.tenantId]:
                self.model[event.tenantId].append(event.sipUri)    
                print(f'Event: {event} processed current model: {self.model}')

        if event.operation == 'remove':
            if event.sipUri in self.model[event.tenantId]:
                self.model[event.tenantId].remove(event.sipUri)    
                print(f'Event: {event} processed current model: {self.model}')
        
class PresenceRequestCommandGenerator:
    def __init__(self, cmdQueue: CommandQueue, subscriberReadModel: SubscriberReadModel) -> None:
        self.cmdQueue = cmdQueue
        self.subscriberReadModel = subscriberReadModel


class CommandProcessor:
    def __init__(self, cmdQueue: CommandQueue, eventStore: EventStore) -> None:
        self.cmdQueue = cmdQueue
        self.eventStore = eventStore

    def start(self):
        return asyncio.create_task(self.__task())

    async def __task(self):
        print('Command processing started')
        try:
            while True:
                cmd = await self.cmdQueue.get()
                print(f'{self.__class__.__name__} fetched command: {cmd}')
                self.eventStore.postEvent(cmd)
        except asyncio.CancelledError:
            print(f'{self.__class__.__name__} command processing task graceful ended')


class API:
    def __init__(self, cmdQueue: CommandQueue) -> None:
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
        self.cmdQueue = CommandQueue()
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
