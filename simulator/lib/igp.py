from dataclasses import dataclass
from typing import List, Dict
from routingAbstractions import AbstractRoutingDaemon
from packet import RoutingPacket,Payload
import networkx as nx

INF = 10000

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
        self._neighbors = {}
        self._lsa_db: Dict[str, LSA] = {}
        self._lsa_queue: Dict[str, List[LSA]] = {}
        self._dups = 0
        self._should_compute_path = False
        self._known_routers = set()
        self._paths = {}
        self._inf = 10000
        self._seq_no = 0  # Initialize sequence number
        self._down_detected_links = []
    
    def compute_path(self):
        if self._id == "r6":
            print("RUNNING DIJKSTRA")
        paths = {router: {"distance": INF, "paths": []} for router in self._lsa_db}
        paths[self._id]["distance"] = 0
        paths[self._id]["paths"] = [[self._id]]
        visited = set()
        routers = list(self._lsa_db.keys())
        while routers:
            router = min(routers, key=lambda r: paths[r]["distance"])
            if paths[router]["distance"] == INF:
                #print(paths)
                print("{} can't reach {}".format(self._id, router))
                #print(self._lsa_db)
                break
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
            # if self._id == "r5":
            #     print("updating table")
            self.update_table(paths)
            self._paths = paths
       # print(paths)
        if self._id == "r6":
            #print(self._lsa_db)
            print(paths)
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
            if rt != ifaces:
                self._fwd_table.setEntry(dest, ifaces) # repalace whole entry if different

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

    ## Interactions with Router object ##

    "Refresher that is run at the beginning of every simulation round."
    def update(self, interfaces2state, currentTime):#TODO determine when to send control plane packets
        if self._id == "r4" and currentTime == 29:
            pass
        # check if ttl expired
        # for r in list(self._lsa_db.keys()):
        #     self._lsa_db[r].ttl -= 1
        #     if self._lsa_db[r].ttl == 0:
        #         self._lsa_db.pop(r)

        # check for link status
        link_state_change = False
        if self._lsa_db.get(self._id):
            my_links = self._lsa_db.get(self._id).links
        else:
            my_links = {}
        new_lsa = LSA(self._seq_no+1, 255, self._id, my_links, False)
        for i, state in interfaces2state.items():    
            if state=="down":
                if i in self._down_detected_links:
                    continue
                else:
                    link_state_change = True
                    self._down_detected_links.append(i)
                    print("{}: {} is down".format(self._id, i))
                    new_links = {}
                    for dest, c in self._lsa_db[self._id].links.items():
                        if dest != self._neighbors[i]:
                            new_links[dest] = c
                    new_lsa.links = new_links
                    print(new_lsa)
                    # for d in self._lsa_db.keys():
                    #     if i in self._fwd_table.getNextHops(d):
                    #         self._fwd_table.removeEntry(d
                    #self.compute_path()
            elif state=="up":
                if i in self._down_detected_links:
                    link_state_change = True
                    self._down_detected_links.remove(i)
                    print("{}: link {} is now up".format(self._id, i))
                    revived_link = {self._neighbors[i]: self._weights[i]}
                    new_lsa.links.update(revived_link)
                    print(new_lsa)
                    print("my db:")
                    print(self._lsa_db)
                    #self.compute_path()
        generate_periodic_lsa = self._fwd_table._table != {} and not currentTime%10

        if link_state_change or (generate_periodic_lsa and self._lsa_db.get(self._id)): # send a lsa if new link down or up detected
            self._lsa_db[self._id] = new_lsa
            self._seq_no += 1
            if link_state_change:
                self.compute_path() 
            for out_iface, d in self._neighbors.items():
                if out_iface in self._lsa_queue.keys(): #and out_iface not in self._down_detected_links:
                    self._lsa_queue[out_iface] = [old_lsa for old_lsa in self._lsa_queue[out_iface] if old_lsa.router_id == self._id and old_lsa.seq >= new_lsa.seq]
                    self._lsa_queue[out_iface].append(new_lsa)
                    self._sentPerInterface[out_iface] = False
                else: #if out_iface not in self._down_detected_links:
                    self._lsa_queue[out_iface] = [new_lsa]
                    self._sentPerInterface[out_iface] = False
            # if self._id == "r4":
            #     print("queue: {}".format(self._lsa_queue))

        # for i, state in interfaces2state.items():
        #     if state=="up":
        #         #  generate a periodic LSA
        #         if (not currentTime%7) and self._lsa_db.get(self._id):
        #             new_lsa = LSA(self._seq_no+1, 255, self._id, self._lsa_db[self._id].links, False)
        #             self._seq_no += 1
        #             self._lsa_queue[i].append(new_lsa)
        #             self._sentPerInterface[i] = False


    "Processor of a new packet received by the router and destined to this routing algorithm."
    def processRoutingPacket(self, packet, iface):
        #print("[IGP] Router {}: I have just received a routing packet with payload {} on interface {}".format(self._id,packet.getPayload().getData(),iface))
        #print("[IGP] router {}: received packet from {}".format(self._id, packet.getSource()))
        if packet.getType() == "BCAST": # hello packet
            self._known_routers.add(packet.getSource())
            new_link = {packet.getSource(): self._weights[iface]} # {destination: cost}'
            current = self._lsa_db.get(self._id)
            if current and packet.getSource() in current.links and current.links[packet.getSource()] == new_link[packet.getSource()]:
                #print("duplicate broadcast")
                return
            if current:
                current.links.update(new_link)
                new_lsa = LSA(self._seq_no+1, 255, self._id, current.links, False)
            elif not current:
                new_lsa = LSA(self._seq_no+1, 255, self._id, new_link, False)
                self._lsa_db[self._id] = new_lsa
            # generate a new LSA about my new link
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

            self._neighbors[iface] = packet.getSource() # {neighbor: interface}
            if iface in self._sentPerInterface:
                del self._sentPerInterface[iface]
            
        if packet.getType() == "routing":
            data: List[LSA] = packet.getPayload().getData() # list of LSAs
            for lsa in data:
                stored = self._lsa_db.get(lsa.router_id)
                if self._id == "r6":
                    print("{} received: {} from {}".format(self._id, lsa, self._neighbors[iface]))
                    print("i have: {}".format(stored))
                if not stored or lsa.seq > stored.seq:
                    self._last_seq_no = lsa.seq
                    stored_links = {} if not stored else stored.links
                    self._known_routers.add(lsa.router_id)
                    for d in lsa.links.keys():
                        self._known_routers.add(d)
                    if self._id == "r6":
                        print("updating my entry")
                    self._lsa_db[lsa.router_id] = lsa
                    print("{} = {}?".format(stored_links, lsa.links))
                    if any(ls not in stored_links for ls in lsa.links) or any(ls not in lsa.links for ls in stored_links):
                        for out_iface, d in self._neighbors.items():
                            if out_iface in self._lsa_queue and out_iface != iface: #send to all interfaces except where it came from
                                self._lsa_queue[out_iface].append(lsa)
                                self._sentPerInterface[out_iface] = False
                            elif out_iface != iface:
                                self._lsa_queue[out_iface] = [lsa]
                                self._sentPerInterface[out_iface] = False
                        self.compute_path()
                    else:
                        print("new lsa with same data")
                        self.compute_path()
                        # new lsa with same data

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
                    entries = self._lsa_queue[iface]
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

