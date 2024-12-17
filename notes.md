# Traceroute
sends probes (packets) that display all the hops on the path between source and destination
first probe expires after 1 hop, second probe expires after 2 hops, and so on
when packet expires, the router that it expired at sends an ICMP error to the sender
this error message is captured - traceroute records the IP address at a each hop and the RTT of that probe

# Routing tables
Routers build tables containing destination, outgoing interface, and metric 
1. destination: IP prefix, i.e. subnet range
2. outgoing interface: which path ID (like port)
3. metric: cost to reach the destination on that interface (set by network admins)
Longest prefix match; pick the destination range that is the most specific given a destination address
If routes have an equal cost then both should be used; each for separate data flows


# How to populate route table
## Startup
Add subnets that it's directly connected to, cost is 0
## Routing protocol
control plane msgs between routers (not application msgs) about how to reach different destinations in the network

Shortest path is important; performance is more important than avoiding loops at L3. Routers are much further away from each other. At L2 loops will lead to a collapse of the network but not L3. 


# Distance Vector
Each router tells everything it knows to its neighbors
Routers send all routing table entries to neighbors

## Pseudocode
When received route for destination D with metric m on interface i
Recall that when a router sends this packet, destination refers to itself

```
m += i.metric
rt = route_table_lookup(D)
if (rt is None): # entry not found
    rt_new = new rt_entry(dest = D, metric = m, interface = i)
    routing_table.add_entry(rt_entry)
else if (m<rt.metric): # destination found, but metric is higher
    rt.metric = m
    rt.interface = i
```

## How it works

A --> B entry about A
B --> C entries about A and B
B --> A entries about A and B

Each router just knows the next hop, i.e. which interface to send a packet on each destination. when protocol converges, each router will have a table that, combined with the other, produces a graph for reaching any destination from any source.

## Link failure
Link between A and B fails
- they both detect the link is down
1. invalidate the entries that use that interface
    - metric = infinity
    - not just the entry for B, but also others that use that interface!
2. sends this updated table to its neighbors (on the remaining links) 
    - when the next DVRP message goes out
3. D (A's neighbor) receives the message
    - in the algorithm so far, D would ignore the msg becuase the path to B is higher (infinity) than what it has
    - D must be forced to update when it receives new info about a destination on interface I, for which the entry it had was I itself 
        - D's table had destination B --> interface 1 
        - it receives msg on interface 1 about destination B
        - therefore it MUST update the entry 
blackhole = one destination is temporarily unreachable by another

first announcement:
4. D will learn how to reach B after receiving a message from E
second announcement:
5. A and B will learn how to reach other; all paths are reconstructed

## Pathologies 
Occur when control plane messages are broadcast in an undesirable order.
A link is broken, but router receives out-of-date msg offering a seemingly better path to that destination that actually relied on the broken link.
### Bouncing
Suppose one link e.g. E-C is much higher than others; operators only want it to be used unless strictly needed

When one of a router's link is broken, e.g. B-C and it receive a message from its neighbors with out of date information that relies on the broken link
It thinks its info is new, updates the entry, and then broadcasts it 
A and B think they can reach C through each other, while E-C is never used
This control plane msg keeps bouncing, and metric keeps increasing until the cost > cost of E-C

### Counting to infinity
A worst case of bouncing: 
What if there is no alternative path? 
Aka one broken link creates a partition of the network

The same bouncing thing as above, but this time there is no limit to when it will stop because there is no alternative path at all, regardless the cost. 
(in real life it would stop at the numerical value assigned to infinity; after that the routers learn that it's unreachable)

--> the only way to address this is by setting a low value for infinity, but then generalizability suffers

## Amending the pathologies
> [!important] 
> These are fundamental to DV, not optional

intuitively: if X uses Y to reach Z, it should never tell Y about its paths to Z

consequence: router's messages to their next hops have to be specially crafted

- Split horizon: X doesn't announce any route to Z on the interface facing Y
- Poison reverse: X tells Y that it's distance to Z is infinity

### Counting to infinity amended, just partially
Using Poison Reverse, the A-D partition has convergence after one announcement

What about BCE partition?

B and C are using E to reach D (but now D is unreachable because E-C is broken)
E's msg about broken link reaches B first, B updates the entry for D to infinity
But before E's msg reaches C, C sends msg to B announcing its path to D, making B think that it offers a better path (undoing the learning of the broken link)

Then B announces to E its path to D (via C), making E think there's a better alternative
--> info about broken link is lost, we are stuck counting to infinity again
--> poison reverse only prevents the loop for 2 routers, not 3+


# Link State
essentially run Dijkstra by every router 
Each router tells everybody (flood) what it knows about your neighbours
- Flood = the neighbors forward the message too

## Hello protocol
send a hello packet on each interface saying that you're following LS protocol
Hello packet contains sender ID, and list of neighbors it has seen on that interface
When a router sees its own ID in a hello message, it knows that it can send packets to that sender (adjacency is up)

## Flooding
Router sends info about its local neighborhood (LSA) on adjacencies that are up 
LSA contains:
- ID of the advertising router
- sequence number
- info about every local link:
    - router ID of the other endpoint
    - metric
routers store LSAs in a Link-State database

### Pseudocode
if link not in db or LSA seq no. > stored seq no.:
    store LSA in db
    flood the LSA on all interface other than the one it arrived on
else if LSA seq no. < stored seq no: # incoming LSA is out of date
    send stored LSA back to the sender # send it latest info
else:
    do nothing
    
> [!tip] 
> Think of LSA as an image of node and their edges. 
The first message is just the sending router (node) and its edges.
The adjacent router will then add to this, so it will forward a graph with the first node, itself as the second node, and each's respective edges.
This way all routers progressively build the graph, i.e. all nodes and edges

Once each router has the map, it calculates the shortest path using Dijkstra and populates routing table

## Pathologies
No bouncing or counting to infinity:

When link fails, router sends complete full map  which is immediately propagated
When network gets partitioned, each router ends up with map of its partition 

### Healed partition 
Suppose DE heals and at the same time BC breaks
D will send LSA about A and C, but doesn't know about BC

Refreshes are inadequate; too often is a lot of overhead, otherwise too slow

--> We cannot relied on the periodicity of flooding esp when state has not changed

Solution: When we have new adjacency, the relevant neighbors exchange summaries of the whole map 
