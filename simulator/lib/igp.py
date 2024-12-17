from dataclasses import dataclass
from routingAbstractions import AbstractRoutingDaemon
from packet import RoutingPacket,Payload

class IGP(AbstractRoutingDaemon):

    ## Initializers ##

    "Constructor"
    def __init__(self):
        self._id = None
        self._sentPerInterface = {}
        self._weights = {} 
        self._fwd_table = {}
        self._metrics = {}
        self._lsa_db = {}
        self._inf = 10000
    
    def get_metric(self, dest):
        try:
            return self._metrics[dest] 
        except KeyError:
            print("Destination {} was not found in metrics".format(dest))
    def set_metric(self, dest, metric):
        self._metrics[dest] = metric

    def rt_lookup(self, dest):
        return self._fwd_table.getNextHops(dest)

    "Setter of router-local parameters specified in the configuration and of options to be applied to all routers"
    def setParameters(self, parameters):
        print("[IGP] Received parameters: {}".format(parameters))
        self._weights = parameters["weights"]

    "Setter of the router ID and reference to forwarding table used to forward packets"
    def bindToRouter(self, router_id, fwd_table):
        self._id = router_id
        print("[IGP] Current forwarding table of {}\n{}".format(router_id,fwd_table.getDescription(router_id)))
        fwd_table.setEntry(router_id, ["local"] )
        self._fwd_table = fwd_table
        self._metrics = {self._id: 0}

    ## Interactions with Router object ##

    "Refresher that is run at the beginning of every simulation round."
    def update(self, interfaces2state, currentTime):#TODO determine when to send control plane packets
        link_down_detected = False
        if "down" in interfaces2state.values():
            link_down_detected = True
        for i, state in interfaces2state.items():
            print("interface {}".format(i))
            print(self._sentPerInterface)
            if state=="down" and not link_down_detected:
                print("{} is down".format(i))
                for d in self._metrics.keys():
                    if i in self._fwd_table.getNextHops(d):
                        self._metrics[d] = self._inf
                        self._fwd_table.removeEntry(d)
            if state=="up" and i in self._sentPerInterface:
                if link_down_detected:
                    print("sending control plane to find new path")
                    del self._sentPerInterface[i]
                    link_down_detected = False
                elif currentTime==1 or not currentTime%5: 
                    del self._sentPerInterface[i]

    "Processor of a new packet received by the router and destined to this routing algorithm."
    def processRoutingPacket(self, packet, iface):
        #print("[IGP] Router {}: I have just received a routing packet with payload {} on interface {}".format(self._id,packet.getPayload().getData(),iface))
        print("[IGP] router {}: received packet from {}".format(self._id, packet.getSource()))
        # DV algorithm
        if packet.getDestination() == "BCAST":
            #d = packet.getSource()
            data = packet.getPayload().getData()[1:]
            for item in data:
                d = item.split(":")[0].split("Destination")[1].strip()
                m = int(item.split(":")[1].split("Metric")[1].strip())
                print("{}: {}".format(d, m))
                m += self._weights[iface]
                rt = self.rt_lookup(d)
                if not rt:
                    print("new entry")
                    self._fwd_table.setEntry(d, [iface])
                    self.set_metric(d, m)
                elif self.get_metric(d) == m and iface not in rt:
                    print("ecmp")
                    self._fwd_table.setEntry(d, rt+[iface])
                elif self.get_metric(d) > m:
                    print("receieved a better path")
                    self._fwd_table.setEntry(d, [iface])
                    self.set_metric(d, m)

    "Generator of control-plane packet to be sent out of the input interface in the current round. It must return a RoutingPacket object, or None (if no packet needs to be sent)."
    def generateRoutingPacket(self, iface):
        pkt = None
        #print(self._sentPerInterface)
        if iface not in self._sentPerInterface:
            print("creating control plane packet")
            self._sentPerInterface[iface] = True
            pkt = RoutingPacket(self._id)
            payload = Payload()
            payload.addEntry("Hello world, here is router {} speaking".format(self._id))
            for d, m in self._metrics.items():
                # split horizon
                if iface not in self._fwd_table.getNextHops(d):
                    payload.addEntry("Destination {}: Metric {}".format(d, m))
            pkt.setPayload(payload)
        # else:
        #     print("loop was skipped")
        return pkt

     ## Traceroute implementation ##

    "Method called by Router, once per traceroute, to get all the packets to send out in order to implement the traceroute."
    def getTracerouteProbes(self, destination):
        return []

    "Method called by Router every time it receives an ICMP packet."
    def processPossibleTracerouteReply(self, icmpPacket):
        pass

    "Method that should return the output of the last completed traceroute."
    def getTracerouteOutput(self):
        return ""

    ## Debug methods ##

    def __str__(self):
        s = "IGP object {}".format(hash(self))
        return s

