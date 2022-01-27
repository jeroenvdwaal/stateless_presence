# CQRS variant 2 prototype
from random import randint
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
        print(f'EventStore event: {data} stored')
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


class SubscriptionReadModel:
    # Read only model build from EventStore events
    # Registers subscribers per tenant

    def __init__(self) -> None:
        self.model = {}

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
    # Generates fetch request, based on the subscription read model
    def __init__(self, cmdQueue: CommandQueue, subscriptionReadModel: SubscriptionReadModel) -> None:
        self.cmdQueue = cmdQueue
        self.subscriptionReadModel = subscriptionReadModel

    async def task(self):
        # read periodically the subscription read model to generate presence fetch commands
        # this should be a smart schedule that allows for scaling
        try:
            while True:
                await asyncio.sleep(3)
                model = self.subscriptionReadModel.model
                for tenantId in model:
                    cmd = DotMap({'operation': 'fetch_presence',
                                 'tenantId': tenantId, 'subscriptions': model[tenantId]})
                    await self.cmdQueue.put(cmd)

        except asyncio.CancelledError:
            print('PresenceRequestCommandGenerator ended gracefully')


class CommandProcessor:
    def __init__(self, cmdQueue: CommandQueue, eventStore: EventStore) -> None:
        self.cmdQueue = cmdQueue
        self.eventStore = eventStore

    async def task(self):
        print('Command processing started')
        try:
            while True:
                cmd = await self.cmdQueue.get()
                print(f'{self.__class__.__name__} fetched command: {cmd}')

                # here we are getting the Teams presence from MS Graph
                if cmd.operation == 'fetch_presence':
                    for subscription in cmd.subscriptions:
                        presence = ['offline', 'online',
                                    'away', 'busy'][randint(0,3)]
                        event = DotMap({'operation': 'presence', 'tenantId': cmd.tenantId,
                               'sipUri': subscription, 'presence': presence})
                        self.eventStore.postEvent(event)
                else:
                    self.eventStore.postEvent(cmd)
        except asyncio.CancelledError:
            print(f'{self.__class__.__name__} command processing task graceful ended')


class API:
    def __init__(self, cmdQueue: CommandQueue, supscriptionReadModel: SubscriptionReadModel) -> None:
        self.cmdQueue = cmdQueue
        self.subscriptionReadModel = supscriptionReadModel

    # Post the operations of the API as commands in the queue
    # Processing will take place down the pipeline.
    async def AddPresenceSubscription(self, tenantId: string, sipUri: string):
        cmd = DotMap(
            {'operation': 'add', 'tenantId': tenantId, 'sipUri': sipUri})
        await self.cmdQueue.put(cmd)

    async def RemovePresenceSubscription(self, tenantId: string, sipUri: string):
        cmd = DotMap(
            {'operation': 'remove', 'tenantId': tenantId, 'sipUri': sipUri})
        await self.cmdQueue.put(cmd)

    # Queries are taken from the read models
    def Subscriptions(self, tenantId: string):
        try:
            return self.subscriptionReadModel.model[tenantId]
        except:
            return []

    def Subscriptions(self):
        return self.subscriptionReadModel.model

    def Tenants(self):
        return self.subscriptionReadModel.model.keys


class PresenceDemo:
    def __init__(self) -> None:
        self.cmdQueue = CommandQueue()
        self.eventStore = EventStore()
        self.cmdProcessor = CommandProcessor(self.cmdQueue, self.eventStore)

        # ReadModels
        self.subscriptionReadModel = SubscriptionReadModel()
        self.eventStore.addSubscriber(self.subscriptionReadModel)

        # API depends on ReadModels
        self.API = API(self.cmdQueue, self.subscriptionReadModel)

        # Fetch presence command generator
        self.presenceRequestCommandGenerator = PresenceRequestCommandGenerator(
            self.cmdQueue, self.subscriptionReadModel)

    def start(self):
        self.taskList = [
            asyncio.create_task(self.cmdProcessor.task()),
            asyncio.create_task(self.presenceRequestCommandGenerator.task())]

    async def stop(self):
        for task in self.taskList:
            task.cancel()
            await task
        print('Demo ended gracefully')


async def main():
    pd = PresenceDemo()
    pd.start()

    await asyncio.sleep(1)
    await pd.API.AddPresenceSubscription('tenant_a', 'sip:agent@nu.nl')
    await asyncio.sleep(20)

    await pd.stop()

asyncio.run(main())
