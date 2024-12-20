import networkx as nx
from dataclasses import dataclass
from typing import List, Dict
from routingAbstractions import AbstractRoutingDaemon
from packet import RoutingPacket,Payload

INF = 10000

@dataclass
class LSA:
    seq: int
    ttl: int
    router_id: str
    links: Dict[str, str]
    dup_received: False

@dataclass
class Hello:
    router_id: str


class IGP(AbstractRoutingDaemon):

    ## Initializers ##

    "Constructor"   
    def __init__(self):
        self._id = None
        self._sentPerInterface = {}
        self._weights = {} 
        self._fwd_table = {}
        self._metrics = {}
        self._links = {}
        self._lsa_db: Dict[str, LSA] = {}
        self._last_lsa: LSA = None
        self._should_compute_path = False
        self._known_routers = set()
        self._paths = {}
        self._inf = 10000
    
    def compute_path(self):
        print("RUNNING DIJKSTRA")
        graph_data = []
        for node, lsa in self._lsa_db.items():
            for link, weight in lsa.links.items():
                edge = (node, link, {"weight": weight})
                graph_data.append(edge)
        graph = nx.DiGraph(graph_data)
        #print(graph_data)
        paths = nx.single_source_dijkstra_path(graph, self._id)
        #print(paths)
        lengths = nx.single_source_dijkstra_path_length(graph, source=self._id)
        if self._paths != paths:
            #print("updating table")
            self.update_table(paths)
            self._paths = paths
        return paths
    
    def update_table(self, paths):
        for dest, hops in paths.items():
            if dest == self._id:
                continue
            if len(hops) > 1 and hops[0] == self._id:
                iface = self._links[hops[1]]
                self._fwd_table.setEntry(dest, [iface])

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
        # TODO check if ttl expired
        link_down_detected = False
        #print("-------------")
        if "down" in interfaces2state.values():
            link_down_detected = True
            #print("{}: checking which interface is down".format(self._id))
            for i, state in interfaces2state.items():
                #print("interface {}".format(i))
                #print(self._sentPerInterface)
                if state=="down":
                    print("{}: {} is down".format(self._id, i))
                    new_lsa = LSA(self._last_lsa.seq+1, 255, self._id, {k: v for k, v in self._lsa_db[self._id].links.items() if self._links.get(k) != i}, False)
                    self._lsa_db[self._id] = new_lsa
                    self._last_lsa = new_lsa

                    print(self._lsa_db)
                    for d in self._lsa_db.keys():
                        if i in self._fwd_table.getNextHops(d):
                            self._fwd_table.removeEntry(d)
            self.compute_path()
        #print("{}: going through ifaces".format(self._id))
        for i, state in interfaces2state.items():
            if state=="up" and i in self._sentPerInterface:
                if link_down_detected:
                    print("sending control plane to find new path")
                    del self._sentPerInterface[i]
                    link_down_detected = False
                    self.generateRoutingPacket(i)
                elif currentTime <= 7 or not currentTime%5:
                    if i in self._sentPerInterface:
                        del self._sentPerInterface[i]
        if self._should_compute_path == True and self._lsa_db:
            self.compute_path()
            self._should_compute_path = False

    "Processor of a new packet received by the router and destined to this routing algorithm."
    def processRoutingPacket(self, packet, iface):
        #print("[IGP] Router {}: I have just received a routing packet with payload {} on interface {}".format(self._id,packet.getPayload().getData(),iface))
        #print("[IGP] router {}: received packet from {}".format(self._id, packet.getSource()))
        if packet.getType() == "BCAST": # hello packet
            print("{} received BCAST".format(self._id))
            self._known_routers.add(packet.getSource())
            new_link = {packet.getSource(): self._weights[iface]} # {destination: cost}'
            current = self._lsa_db.get(self._id)
            if not current:
                self._last_lsa = LSA(packet.getSequenceNumber(), packet.getTtl(), self._id, new_link, False)
                self._lsa_db[self._id] = self._last_lsa
            else:
                current.links.update(new_link)
                self._last_lsa = LSA(packet.getSequenceNumber(), packet.getTtl(), self._id, current.links, False)
            self._links[packet.getSource()] = iface # {neighbor: interface}
            print(self._lsa_db)
            
            
        if packet.getType() == "routing":
            data: List[LSA] = packet.getPayload().getData() # list of LSAs
            for lsa in data:
                if lsa.router_id == "r2":
                    print("{} received: {}".format(self._id, lsa))
                stored = self._lsa_db.get(lsa.router_id)
                #print("i have: {}".format(stored))
                if not stored or lsa.seq > stored.seq:
                    self._last_seq_no = lsa.seq
                    stored_links = {} if not stored else stored.links
                    if any(ls not in stored_links for ls in lsa.links) or any(ls not in lsa.links for ls in stored_links):
                    # diff = stored_links.symmetric_difference(set(lsa.links))
                    # if diff: # not identical 
                        self._known_routers.add(lsa.router_id)
                        for d in lsa.links.values():
                            self._known_routers.add(d)
                        self._lsa_db[lsa.router_id] = lsa
                        print("flooding the lsa:")
                        print(lsa)
                        self._sentPerInterface[iface] = True
                        self._sentPerInterface = {iface: self._sentPerInterface[iface]}
                        self._last_lsa = lsa
                        self._should_compute_path = True
                elif lsa.seq < stored.seq:
                    print("sending an updated lsa on interface {}".format(iface))
                    if iface in self._sentPerInterface:
                        del self._sentPerInterface[iface]
                    self.generateRoutingPacket(iface) # TODO
                else:
                    # repeated lsa, run dijkstra if first time
                    print("lsa already exists") 
                    stored.dup_received = True
                    #self._should_compute_path = False
                    # if self._should_compute_path: 
                    #     self.compute_path()
                    #     self._should_compute_path = False


    "Generator of control-plane packet to be sent out of the input interface in the current round. It must return a RoutingPacket object, or None (if no packet needs to be sent)."
    def generateRoutingPacket(self, iface):
        pkt = None
        #print(self._sentPerInterface)
        if iface not in self._sentPerInterface:
            self._sentPerInterface[iface] = True
            pkt = RoutingPacket(self._id)
            payload = Payload()
            if self._last_lsa == None:
                print("{} creating hello packet".format(self._id))
                payload.addEntry("Hello world, here is router {} speaking".format(self._id))
                pkt.setType("BCAST")
            else:
                print("{} creating lsa packet on interface {}".format(self._id, iface))
                payload.addEntry(self._last_lsa)
                pkt.setType("routing")

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

