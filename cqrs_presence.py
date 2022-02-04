# CQRS variant 2 prototype
from random import randint
import asyncio
from dotmap import DotMap
import logging

# Classes that represents resources


class BaseReadModel:
    def __init__(self) -> None:
        self.model = {}

    def update(self, event):
        # Notify inheritor to implement this method
        raise NotImplementedError("Please implement this method")


class EventStore:
    # Simple observer model represents the event store.
    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self.store = []
        self.readModels = []

    def addModel(self, readModel: BaseReadModel):
        self.readModels.append(readModel)

    def postEvent(self, event):
        self.logger.info(f'Event \'{event}\' stored')
        self.store.append(event)
        for subscriber in self.readModels:
            subscriber.update(event)


class CommandQueue:
    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self.queue = asyncio.Queue()

    async def put(self, cmd):
        self.logger.info(f'Command \'{cmd}\' added to queue')
        await self.queue.put(cmd)

    async def get(self):
        cmd = await self.queue.get()
        self.logger.info(f'Command \'{cmd}\' fetched from queue')
        return cmd

# Application classes


class SubscriptionReadModel(BaseReadModel):
    # Read only model build from EventStore events
    # Registers subscribers per tenant

    def __init__(self) -> None:
        super().__init__()
        self.logger = logging.getLogger(self.__class__.__name__)

    def update(self, event):
        # Add empty set if tenant is not known
        if event.operation == 'add':
            if event.tenantId not in self.model:
                self.model[event.tenantId] = []

            if event.sipUri not in self.model[event.tenantId]:
                self.model[event.tenantId].append(event.sipUri)
                self.logger.info(
                    f'Event: {event} processed current model: {self.model}')

        if event.operation == 'remove':
            if event.sipUri in self.model[event.tenantId]:
                self.model[event.tenantId].remove(event.sipUri)

                if len(self.model[event.tenantId]) == 0:
                    del self.model[event.tenantId]
                    
                self.logger.info(
                    f'Event: {event} processed current model: {self.model}')



class PresenceRequestCommandGenerator:
    # Generates fetch request, based on the subscription read model
    def __init__(self, cmdQueue: CommandQueue, subscriptionReadModel: SubscriptionReadModel) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
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
            self.logger.info(
                'Ended gracefully')


class CommandProcessor:
    def __init__(self, cmdQueue: CommandQueue, eventStore: EventStore) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self.cmdQueue = cmdQueue
        self.eventStore = eventStore

    async def task(self):
        self.logger.info('Processing started')
        try:
            while True:
                cmd = await self.cmdQueue.get()
                self.logger.info(
                    f'Fetched command: {cmd}')

                # here we are getting the Teams presence from MS Graph
                if cmd.operation == 'fetch_presence':
                    for subscription in cmd.subscriptions:
                        presence = ['offline', 'online',
                                    'away', 'busy'][randint(0, 3)]
                        event = DotMap({'operation': 'presence', 'tenantId': cmd.tenantId,
                                        'sipUri': subscription, 'presence': presence})
                        self.eventStore.postEvent(event)
                else:
                    self.eventStore.postEvent(cmd)
        except asyncio.CancelledError:
            self.logger.info(
                f'Ended gracefully')


class API:
    def __init__(self, cmdQueue: CommandQueue, supscriptionReadModel: SubscriptionReadModel) -> None:
        self.cmdQueue = cmdQueue
        self.subscriptionReadModel = supscriptionReadModel

    # Post the operations of the API as commands in the queue
    # Processing will take place down the pipeline.
    async def AddPresenceSubscription(self, tenantId: str, sipUri: str):
        cmd = DotMap(
            {'operation': 'add', 'tenantId': tenantId, 'sipUri': sipUri})
        await self.cmdQueue.put(cmd)

    async def RemovePresenceSubscription(self, tenantId: str, sipUri: str):
        cmd = DotMap(
            {'operation': 'remove', 'tenantId': tenantId, 'sipUri': sipUri})
        await self.cmdQueue.put(cmd)

    # Queries are taken from the read models
    def Subscriptions(self, tenantId: str):
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
        self.logger = logging.getLogger(self.__class__.__name__)
        self.cmdQueue = CommandQueue()
        self.eventStore = EventStore()
        self.cmdProcessor = CommandProcessor(self.cmdQueue, self.eventStore)

        # ReadModels
        self.subscriptionReadModel = SubscriptionReadModel()
        self.eventStore.addModel(self.subscriptionReadModel)

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
        self.logger.info('Demo ended gracefully')


async def main():
    pd = PresenceDemo()
    pd.start()

    await asyncio.sleep(1)
    await pd.API.AddPresenceSubscription('tenant_a', 'sip:agent@nu.nl')
    await asyncio.sleep(5)
    await pd.API.RemovePresenceSubscription('tenant_a', 'sip:agent@nu.nl')
    await asyncio.sleep(5)

    await pd.stop()


logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s [%(name)s] %(message)s')
asyncio.run(main())
