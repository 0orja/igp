from dataclasses import dataclass
from typing import List, Dict
from routingAbstractions import AbstractRoutingDaemon
from packet import RoutingPacket,Payload
import networkx as nx

INF = 10000
test_routers = ["Newark", "Phoenix,","SaltLakeCity", "Dallas", "Chicago", "Rochester","WashingtonDC", "Minneapolis"]

@dataclass
class LSA:
    seq: int
    ttl: int
    router_id: str
    links: Dict[str, str]
    dup_received: False

class IGP(AbstractRoutingDaemon):

    ## Initializers ##

    "Constructor"   
    def __init__(self):
        self._id = None
        self._sentPerInterface = {}
        self._weights = {} 
        self._fwd_table = {}
        self._metrics = {}
        self._neighbors = {}
        self._lsa_db: Dict[str, LSA] = {}
        self._lsa_queue: Dict[str, List[LSA]] = {}
        self._dups = 0
        self._should_compute_path = False
        self._known_routers = set()
        self._paths = {}
        self._inf = 10000
        self._seq_no = 0  # Initialize sequence number
    
    def compute_path(self):
        #print("RUNNING DIJKSTRA")
        #print(self._lsa_db)
        paths = {router: {"distance": INF, "paths": []} for router in self._lsa_db}
        paths[self._id]["distance"] = 0
        paths[self._id]["paths"] = [[self._id]]
        visited = set()
        routers = list(self._lsa_db.keys())
        while routers:
            router = min(routers, key=lambda r: paths[r]["distance"])
            #print(router)
            if paths[router]["distance"] == INF:
                #print(paths)
                continue
            #print(f"Processing router: {router}, current distance: {paths[router]['distance']}")
            visited.add(router)
            lsa = self._lsa_db[router]
            for dest, cost in lsa.links.items():
                dist = paths[router]["distance"] + cost
                existing = paths.get(dest)
                if existing:
                    existing = existing["distance"]
                else:
                    existing = INF
                if dist < existing:
                    if existing == INF:
                        paths[dest] = {"distance": INF, "paths": []}
                    paths[dest]["distance"] = dist
                    paths[dest]["paths"] = [path + [dest] for path in paths[router]["paths"]]
                elif dist == existing:
                    paths[dest]["paths"].extend(
                        [path + [dest] for path in paths[router]["paths"]]
                    )
            routers.remove(router)
        #print("done")
        if self._paths != paths:
            self.update_table(paths)
            self._paths = paths
       # print(paths)
        return paths
    
    def update_table(self, paths):
        #print(paths)
        for dest, path in paths.items():
            if dest == self._id:
                continue
            rt = self.rt_lookup(dest)
            ifaces = []
            for p in path["paths"]:
                if len(p) > 1 and p[0] == self._id:
                    for interface, neighbor in self._neighbors.items():
                        if neighbor == p[1]:
                            ifaces.append(interface)
            for i in ifaces:
                if i not in rt:
                    self._fwd_table.setEntry(dest, ifaces) # repalace whole entry if any iface is misisng

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
        self._neighbors = {iface: None for iface in parameters["weights"].keys()}

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
        for r in list(self._lsa_db.keys()):
            self._lsa_db[r].ttl -= 1
            if self._lsa_db[r].ttl == 0:
                self._lsa_db.pop(r)


        link_down_detected = False
        if "down" in interfaces2state.values():
            link_down_detected = True
            #print("{}: checking which interface is down".format(self._id))
            for i, state in interfaces2state.items():
                #print("interface {}".format(i))
                #print(self._sentPerInterface)
                if state=="down":
                    print("{}: {} is down".format(self._id, i))
                    new_lsa = LSA(self._seq_no+1, 255, self._id, {k: v for k, v in self._lsa_db[self._id].links.items() if self._neighbors.get(i) != k}, False)
                    print(new_lsa)
                    self._lsa_db[self._id] = new_lsa
                    self._seq_no += 1
                    for out_iface, d in self._neighbors.items():
                        if out_iface in self._lsa_queue.keys() and out_iface != i:
                            self._lsa_queue[out_iface].append(new_lsa)
                            self._sentPerInterface[out_iface] = False
                        elif out_iface != i:
                            self._lsa_queue[out_iface] = [new_lsa]
                            self._sentPerInterface[out_iface] = False

                    #print(self._lsa_db)
                    for d in self._lsa_db.keys():
                        if i in self._fwd_table.getNextHops(d):
                            self._fwd_table.removeEntry(d)
            print("computing new path")
            self.compute_path()
        #print("{}: going through ifaces".format(self._id))
        for i, state in interfaces2state.items():
            if state=="up" and i in self._sentPerInterface:
                if link_down_detected:
                    print("sending control plane to find new path")
                    del self._sentPerInterface[i]
                    link_down_detected = False
                    self.generateRoutingPacket(i)
                elif currentTime <= 15 or not currentTime%5:
                    if i in self._sentPerInterface:
                        del self._sentPerInterface[i]


    "Processor of a new packet received by the router and destined to this routing algorithm."
    def processRoutingPacket(self, packet, iface):
        #print("[IGP] Router {}: I have just received a routing packet with payload {} on interface {}".format(self._id,packet.getPayload().getData(),iface))
        #print("[IGP] router {}: received packet from {}".format(self._id, packet.getSource()))
        if packet.getType() == "BCAST": # hello packet
            if self._id=="Phoenix" or self._id=="Dallas":
                print("{} received BCAST from {}".format(self._id, packet.getSource()))
            self._known_routers.add(packet.getSource())
            new_link = {packet.getSource(): self._weights[iface]} # {destination: cost}'
            current = self._lsa_db.get(self._id)
            if current and packet.getSource() in current.links and current.links[packet.getSource()] == new_link[packet.getSource()]:
                #print("duplicate broadcast")
                return
            if current:
                current.links.update(new_link)
                new_lsa = LSA(self._seq_no+1, 255, self._id, current.links, False)
                if self._id=="Phoenix" or self._id=="Dallas":
                    print("updating my existing lsa db entry")
            elif not current:
                new_lsa = LSA(self._seq_no+1, 255, self._id, new_link, False)
                if self._id=="Phoenix" or self._id=="Dallas":
                    print("new lsa db self entry: {}".format(new_lsa))
                self._lsa_db[self._id] = new_lsa
            # generate a new LSA about my new link
            #print(new_lsa)
            self._seq_no += 1
            for out_iface, d in self._neighbors.items(): # send to all interfaces
                if out_iface in self._lsa_queue.keys():
                    # flush outdated LSAs in the queue
                    self._lsa_queue[out_iface] = [old_lsa for old_lsa in self._lsa_queue[out_iface] if old_lsa.router_id == self._id and old_lsa.seq >= new_lsa.seq]
                    self._lsa_queue[out_iface].append(new_lsa)
                    self._sentPerInterface[out_iface] = False
                else:
                    self._lsa_queue[out_iface] = [new_lsa]
                    self._sentPerInterface[out_iface] = False
            # if self._id=="Phoenix" or self._id=="SaltLakeCity":
            #     print("{} lsa queue: {}".format(self._id, self._lsa_queue))

            self._neighbors[iface] = packet.getSource() # {neighbor: interface}
            if iface in self._sentPerInterface:
                del self._sentPerInterface[iface]
            
        if packet.getType() == "routing":
            data: List[LSA] = packet.getPayload().getData() # list of LSAs
            for lsa in data:
                if self._id == "Phoenix" or self._id == "Dallas":
                    print("{} received: {} from {}".format(self._id, lsa, self._neighbors[iface]))
                stored = self._lsa_db.get(lsa.router_id)
                #print("i have: {}".format(stored))
                if not stored or lsa.seq > stored.seq:
                    self._last_seq_no = lsa.seq
                    stored_links = {} if not stored else stored.links
                    if any(ls not in stored_links for ls in lsa.links) or any(ls not in lsa.links for ls in stored_links):
                        if self._id == "Phoenix" or self._id == "Dallas":
                            print("new link detected")
                        self._known_routers.add(lsa.router_id)
                        for d in lsa.links.keys():
                            self._known_routers.add(d)
                        self._lsa_db[lsa.router_id] = lsa
                        #print(lsa)
                        #self._sentPerInterface[iface] = True
                       # self._sentPerInterface = {iface: self._sentPerInterface[iface]}
                        for out_iface, d in self._neighbors.items():
                            if out_iface in self._lsa_queue and out_iface != iface: #send to all interfaces except where it came from
                                self._lsa_queue[out_iface].append(lsa)
                                self._sentPerInterface[out_iface] = False
                            elif out_iface != iface:
                                self._lsa_queue[out_iface] = [lsa]
                                self._sentPerInterface[out_iface] = False
                        
                        self.compute_path()
                elif lsa.seq < stored.seq:
                    #print("sending an updated lsa on interface {}".format(iface))
                    self._sentPerInterface[iface] = False
                    if iface in self._lsa_queue:
                        self._lsa_queue[iface].append(stored)
                    else:
                        self._lsa_queue[iface] = [stored]
                    #self.generateRoutingPacket(iface) # TODO
                else:
                    # repeated lsa, run dijkstra if first time
                   #print("lsa already exists") 
                    if self._id == "Phoenix" or self._id == "Dallas":
                        print("{} already knows about {}".format(self._id, lsa.router_id))
                    stored.dup_received = True
                    self._dups += 1
                    # TODO add iface back to list
                    
    "Generator of control-plane packet to be sent out of the input interface in the current round. It must return a RoutingPacket object, or None (if no packet needs to be sent)."
    def generateRoutingPacket(self, iface):
        pkt = None
        if iface not in self._sentPerInterface or self._sentPerInterface[iface] == False:
            self._sentPerInterface[iface] = True

            if not self._lsa_queue:
                pkt = RoutingPacket(self._id)
                payload = Payload()
                #print("{} creating hello packet on {}".format(self._id, iface))
                payload.addEntry("Hello world, here is router {} speaking".format(self._id))
                pkt.setType("BCAST")
            else:
                #print("{} creating lsa packet on interface {} with payload".format(self._id, iface))
                pkt = RoutingPacket(self._id)
                payload = Payload()
                if self._lsa_queue.get(iface):
                    if self._id == "Phoenix" or self._id == "Dallas":
                        pass
                    entries = self._lsa_queue[iface]
                    # if self._id == "Phoenix" or self._id == "Dallas":
                    #     print("{} is sending an lsa to {} about {}".format(self._id, self._neighbors[iface], entry.router_id))
                    #pkt.setSequenceNumber(entry.seq)  # Increment sequence number for new LSA
                    for lsa in entries:
                        payload.addEntry(lsa)
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

