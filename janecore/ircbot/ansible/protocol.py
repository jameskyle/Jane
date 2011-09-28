import pickle

from twisted.internet.protocol import Protocol
from twisted.protocols import amp
from twisted.python import log
from twisted.internet import defer, reactor
import commands

class AnsibleProtocol(amp.AMP):
    """
    Protocol to allow a bot plugin client communicate
    with a Jane server.
    """
    timeout=300
    def connectionMade(self):
        if self.factory.number_of_connections >= self.factory.max_connections:
            self.transport.write("Too many active plugins.")
            log.msg("Dropping plugin connection attempt")
            self.transport.oseConnection()
            return
        
        self.factory.number_of_connections += 1
        self.identifier = self.factory.number_of_connections

        # TODO: should try to let the other side know why they're being
        # disconnected.
        self.timeout_deferred = reactor.callLater(self.__class__.timeout,
                self.transport.loseConnection)
        amp.AMP.connectionMade(self)
    
    @defer.inlineCallbacks
    def callback(self, evt):
        print "Ansible callback fired" 
        data = pickle.dumps(evt.data)
        print data
        res = yield self.callRemote(commands.EventFired,event_name=evt.__class__.EVENT, data=data)
        print res
        defer.returnValue(evt)

    @commands.RegisterListener.responder
    def register_listener(self, event_name):
        print("register_listener called")
        self.factory.evt_mgr.addListener(event_name, self.callback)
        return {}

    @commands.DispatchEvent.responder
    def dispatchEvent(self, event_name, data):
        self.factory.evt_mgr.dispatch(event_name, pickle.loads(data))
        return {}

class AnsibleClientProtocol(amp.AMP):
    """ Base client protocol for jane's ansible plugin system"""
    EVENTS = []
    def __init__(self):

        # {eventname : callback method}
        self.remote_event_registry = {}
    
    def connectionMade(self):
        """ Called when connection made """
        print ("Ansible plugin connected to server")
        for event in self.__class__.EVENTS:
            try:
                self.registerRemote(event, getattr(self, event + "Callback"))
            except AttributeError:
                print "Event callback not found, skipping: %s" % event
    
    @defer.inlineCallbacks
    def registerRemote(self, eventname, callback):
        print "trying to register %s" % eventname
        res = yield self.callRemote(commands.RegisterListener, event_name=eventname)
        self.remote_event_registry[eventname] = callback

    @commands.EventFired.responder
    def eventFired(self, event_name, data):
        """
        Called when a remote event that we've registered for
        has fired. Data is a pickled data structure or basic
        type.
        """
        data = pickle.loads(data)
        print "eventfired fired with %s" % data
        if not event_name in self.remote_event_registry:
            raise ValueError("Received event that's not registered locally")
        reactor.callLater(0, self.remote_event_registry[event_name], data)  
        return {}