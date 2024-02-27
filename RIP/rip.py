"""
Description:
This programme is to implement a simplified RIP.
More than one instances can run parallelly under a Linux-like operating system on the same machine -
each instance runs as a separate process, and these processes communicate through local sockets.

"""
import sys
import socket
import selectors
import threading
import logging
import random

# For debug
#logging.basicConfig(level=logging.DEBUG, format='(%(threadName)-9s) %(message)s',)

INFINITE_METRIC = 16
PERIODIC_UPDATE_TIMER_INTERVAL = 7
TIMEOUT_TIMER_INTERVAL = PERIODIC_UPDATE_TIMER_INTERVAL * 6
GARBAGE_COLLECTION_TIMER_INTERVAL = PERIODIC_UPDATE_TIMER_INTERVAL * 4

class ResponseMessage:
    """
    This class defines the structure of a response message which is used for communicating with
    peer routers.
    """

    class RIPEntry:
        """
        This class defines the structure of a rip entry
        """
        def __init__(self, route=None):
            """
            Initialise all the fields in rip entry
            Note: 1. Only AF_INET is supported.
                  2. According to the requirement of assignment,
                     the field of "ip_address" should be filled in router id
            """
            self.address_family_identifier = 2

            if route != None:
                self.dest_router_id = route.dest
                self.next_hop = route.neighbor
                self.metric = route.metric


        def __str__(self):
            """
            Format the entry into a string for debugging
            """
            return "AFI: {}    Dest: {}    Next hop: {}    Metric: {}\n"\
                .format(self.address_family_identifier, self.dest_router_id, self.next_hop, self.metric)
    

    def __init__(self, router_id=0):
        """
        Initialise a response message which contains a header and a body
        Note: 1. Only support response message
              2. The version number is always 2
              3. The body comprises 25 rip entries at most
        """
        # header
        self.command = 2
        self.version = 2
        self.sending_router_id = router_id

        # body - rip entries
        self.rip_entries = []


    def add_rip_entry(self, route):
        """
        Generate a rip entry according to a routing table entry.
        """
        entry = self.RIPEntry(route)
        self.rip_entries.append(entry)


    def encode(self):
        """
        Encode the message into binary stream which is used for tranmission
        """
        # According to RIP, Every message compirses one header and 1~25 RIP entries.
        # Header accounts for 4 bytes and every RIP entry accounts for 20 bytes
        message = bytearray(4 + 20 * len(self.rip_entries))

        # Assemble header data
        message[0] = self.command
        message[1] = self.version

        # We use 16 bits to store sending router id, so the id value is divided into 2 parts
        message[2] = self.sending_router_id & 255
        message[3] = (self.sending_router_id) >> 8 & 255

        # Assemble RIP entries
        start_index = 4
        for entry in self.rip_entries:
            # Address family identifier field(2)
            message[start_index] = entry.address_family_identifier & 255
            message[start_index + 1] = 0

            # must be zero (2)
            message[start_index + 2] = 0
            message[start_index + 3] = 0

            # IPv4 address (4)
            # In this programe, we use router id instead (16 bits)
            message[start_index + 4] = entry.dest_router_id & 255
            message[start_index + 5] = (entry.dest_router_id >> 8) & 255
            message[start_index + 6] = 0
            message[start_index + 7] = 0

            # Subnet Mask (4)
            message[start_index + 8] = 0
            message[start_index + 9] = 0
            message[start_index + 10] = 0
            message[start_index + 11] = 0

            # Next Hop (4)
            # In this programe, we use router id instead (16 bits)
            message[start_index + 12] = entry.next_hop & 255
            message[start_index + 13] = (entry.dest_router_id >> 8) & 255
            message[start_index + 14] = 0
            message[start_index + 15] = 0

            # Metric (4)
            message[start_index + 16] = entry.metric & 255
            message[start_index + 17] = 0
            message[start_index + 18] = 0
            message[start_index + 19] = 0

            start_index += 20

        return message
    

    def decode(self, data):
        """
        Decode the message stream
        """
        # Parse RIP response message header
        self.command = data[0]
        if self.command != 2:
            print("ResponseMessage:decode - wrong command")
            return False

        self.version = data[1]
        if self.version != 2:
            print("ResponseMessage:decode - wrong version")
            return False

        self.sending_router_id = data[2] + data[3] * 256
        if self.sending_router_id > 64000 or self.sending_router_id < 1:
            print("ResponseMessage:decode - wrong sending router id")
            return False

        # Parse RIP entries
        # Header accounts for 4 bytes and every RIP entry accounts for 20 bytes
        entry_number = (len(data) - 4) // 20
        start_index = 4

        for i in range(entry_number):
            entry = self.RIPEntry()

            # Address family identifier field(2)
            entry.address_family_identifier = data[start_index]
            if entry.address_family_identifier != 2:
                print("ResponseMessage:decode - wrong AFI")
                return False

            # IPv4 address (4)
            # In this programe, we use router id instead (16 bits)
            entry.dest_router_id = data[start_index + 4] + data[start_index + 5] * 256
            if entry.dest_router_id > 64000 or entry.dest_router_id < 1:
                print("ResponseMessage:decode - wrong destination router id")
                return False

            # Next Hop (4)
            # In this programe, we use router id instead (16 bits)
            entry.next_hop = data[start_index + 12] + data[start_index + 13] * 256
            if entry.next_hop > 64000 or entry.next_hop < 1:
                print("ResponseMessage:decode - wrong next_hop")
                return False

            # Metric (4)
            entry.metric = data[start_index + 16]
            if entry.metric > INFINITE_METRIC or entry.next_hop < 1:
                print("ResponseMessage:decode - wrong metric")
                return False

            self.rip_entries.append(entry)

            start_index += 20

        return True


    def __str__(self):
        """
        Format the message into a string for debugging
        """
        header = "\n-----------------------------------------------------------\n"
        header += "Command: {}    Version: {}    Src: {}\n".format(self.command, self.version, self.sending_router_id)
        for entry in self.rip_entries:
            header += "-----------------------------------------------------------\n"
            header += str(entry)
        header += "-----------------------------------------------------------\n"
        
        return header


class Connection:
    """
    This class is to create a udp "connection" between current router and its neighbor
    """
    def __init__(self, sending_router_id, neighbor_router_id, input_port, output_port, metric):
        """
        Establish a connection with its neighbor
        """
        self.ip = "127.0.0.1"
        self.sending_router_id = sending_router_id
        self.neighbor_router_id = neighbor_router_id
        self.metric = metric

        self.input_port = input_port
        self.input_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.input_socket.bind((self.ip, self.input_port))

        self.output_port = output_port
        self.output_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


    def close(self):
        """
        Close current socket
        """
        self.input_socket.close()
        self.output_socket.close()


    def receive_routing_table_entries_from_neighbor(self):
        """
        Reveive messages from a neighbor
        """
        data = self.input_socket.recvfrom(1024)[0]
    
        response_message = ResponseMessage()
        result = response_message.decode(data)
        if not result:
            print("Decode message failed!")
            return None

        # For debugging
        # print("received message (string):", str(response_message))

        # Conver response message into routing table entries
        routes = []
        for entry in response_message.rip_entries:
            route = Route(response_message.sending_router_id, entry.dest_router_id, entry.next_hop, entry.metric)
            routes.append(route)

        return routes


    def send_routing_table_entries_to_neighbor(self, routes):
        """
        Send messages to a neighbor
        There is a limit of 25 RTEs to a Response; if there are more, send the current Response and start a new one. 
        """
        message_count = len(routes) // 25
        if len(routes) % 25 != 0:
            message_count += 1

        for i in range(message_count):
            message = ResponseMessage(self.sending_router_id)

            start_index = i * 25
            for index in range(start_index, len(routes)):
                route = routes[index]
                sending_route = Route(route.src, route.dest, route.neighbor, route.metric)
            
                # Do split horizon with poisoned reverse process except that the destination is its neighbor
                if route.neighbor == self.neighbor_router_id and route.dest != self.neighbor_router_id:
                    sending_route.metric = INFINITE_METRIC
        
                message.add_rip_entry(sending_route)

            # Fix bug
            # Add an extra route data which represents the direct connection
            # This data is useful in this situation:
            # When the metric to one of destinations is lower than the route via its current neighbor( the owner of current input port)
            # it will lose information when current route becomes invalid and have to choose its current neighbor insteam.
            sending_route = Route(self.sending_router_id, self.neighbor_router_id, self.neighbor_router_id, self.metric)
            message.add_rip_entry(sending_route)
    
            data = message.encode()

            # For debugging
            # print("sent message (string):", str(message))

            self.output_socket.sendto(data, 0, (self.ip, self.output_port))


class Route:
    """
    This class defines a vaild route from the view of current router
    """
    def __init__(self, src, dest, neighbor, metric):
        """
        Initialise a rip daemon
        """
        self.src = src
        self.dest = dest
        self.neighbor = neighbor
        self.metric = metric
        self.timeout_callback = None
        self.timeout_timer = None


    def activate_timeout_timer(self, callback):
        """
        Activate timer for next timeout notification
        """
        if self.timeout_timer != None and self.timeout_timer.is_alive():
            self.timeout_timer.cancel()
    
        self.timeout_callback = callback
        self.timeout_timer = threading.Timer(TIMEOUT_TIMER_INTERVAL, self.trigger_timeout)
        self.timeout_timer.start()


    def trigger_timeout(self):
        """
        This function indicates that current path is invalid and need to notify host to trigger a garbage collection process
        """
        self.timeout_callback(self.neighbor, self.dest)


    def __str__(self):
        """
        Format a route to a string which is convenient for transmitting
        """
        return '{} "src": {}, "dest": {}, "via": {}, "metric": {} {}\n'.format("{", self.src, self.dest, self.neighbor, self.metric, "}")


class RIPDaemon:
    """
    This class is to implement a daemon which complys to a simplified RIP
    """
    def __init__(self, file_name):
        """
        Initialise a rip daemon
        """
        self.garbage_collection_timers = []
        self.triggered_update_timers = []
        self.periodic_update_timer = None
        self.lock = threading.Lock()

        # Parse configuration file to extract router id, input ports and outputs
        (result, self.id, input_ports, self.outputs) = self.load_config_file(file_name)
        if not result:
            print("Fail to parse config file!")
            exit(1)

        # Initialise all the valid routes
        # At first the valid routes only the routes to its neighbors
        self.routes = []
        for index in range(len(input_ports)):
            input_port = input_ports[index]
            output_port, metric, neightbor = self.outputs[index]
            route = Route(self.id, neightbor, neightbor, metric)
            route.activate_timeout_timer(self.timeout_timer_callback)
            self.routes.append(route)

        # Initialise all socket with neighbors
        self.connections = []
        self.selector = selectors.DefaultSelector()
        for index in range(len(input_ports)):
            input_port = input_ports[index]
            output_port, metric, neightbor = self.outputs[index]
    
            connection = Connection(self.id, neightbor, input_port, output_port, metric)
            self.connections.append(connection)

            # Register read event to current selector
            # The reason why we do not register write event is to avoid infitite loop when activating this rip daemon.
            self.selector.register(connection.input_socket, selectors.EVENT_READ)

        self.print_routing_table()


    def __del__(self):
        """
        Clean useless resources
        """
        # Unregister read and write event
        for connection in self.connections:
            self.selector.unregister(connection.input_socket)
            self.selector.unregister(connection.output_socket)
            connection.close()

        self.selector.close()
        self.periodic_update_timer.cancel()

        for i in range(len(self.garbage_collection_timers)):
            timer = self.garbage_collection_timers[i][0]
            timer.cancel()

        for timer in self.triggered_update_timers:
            timer.cancel()


    def load_config_file(self, file_name):
        """
        load and parse config file
        """
        # Load config file
        route_id = 0
        input_ports = []
        outputs = []
    
        try: 
            file = open(file_name)
        except FileNotFoundError:
            print(file_name, "does not exist!")
            return (False, route_id, input_ports, outputs)
        else:
            lines = []
            raw_lines = file.readlines()
            for line in raw_lines:
                # Filter empty lines and comments
                if len(line.strip()) != 0 and not line.strip().startswith('#'):
                    lines.append(line.strip())
            file.close()

            if len(lines) < 3:
                print("Invalid config file!")
                return (False, route_id, input_ports, outputs)

            # Parse router id
            first_line_data = lines[0].split()
            if len(first_line_data) < 2 or first_line_data[0] != "router-id":
                print("Wrong router id format!")
                return (False, route_id, input_ports, outputs)

            route_id = first_line_data[1]
            if not route_id.isdecimal() or int(route_id) < 1 or int(route_id) > 64000:
                print("Wrong router id!")
                return (False, route_id, input_ports, outputs)

            # Parse input ports
            second_line_data = lines[1].split()
            if len(second_line_data) < 2 or second_line_data[0] != "input-ports":
                print("Wrong input-ports format!")
                return (False, route_id, input_ports, outputs)

            for index in range(1, len(second_line_data)):
                port = second_line_data[index].strip(',')
                if not port.isdecimal() or int(port) < 1024 or int(port) > 64000:
                    print("Wrong port number!")
                    return (False, route_id, input_ports, outputs)
                input_ports.append(int(port))
            
            # Make sure that each port number occurs at most once.
            input_ports_set = set(input_ports)
            if len(input_ports_set) != len(input_ports):
                print("Duplicated port number!")
                return (False, route_id, input_ports, outputs)

            # Parse outputs
            third_line_data = lines[2].split()
            if len(third_line_data) < 2 or third_line_data[0] != "outputs":
                print("Wrong outputs format!")
                return (False, route_id, input_ports, outputs)

            for index in range(1, len(third_line_data)):
                port, metric, neighbor_id = third_line_data[index].strip(',').split('-')

                if not port.isdecimal() or int(port) < 1024 or int(port) > 64000 or int(port) in input_ports:
                    print("Wrong port number!")
                    return (False, route_id, input_ports, outputs)

                if not metric.isdecimal() or int(metric) < 1 or int(metric) > 16:
                    print("Wrong metric number!")
                    return (False, route_id, input_ports, outputs)

                if not neighbor_id.isdecimal() or int(neighbor_id) < 1 or int(neighbor_id) > 64000:
                    print("Wrong neighbor router id!")
                    return (False, route_id, input_ports, outputs)
    
                outputs.append((int(port), int(metric), int(neighbor_id)))

            # Make sure that the input and output ports are one-to-one
            if len(input_ports) != len(outputs):
                print("input and output ports are not one-to-one!")
                return (False, route_id, input_ports, outputs)
            
            return (True, int(route_id), input_ports, outputs)


    def activate(self):
        """
        Enable the ability of sending messages and receiving messages to its neighbor
        """
        self.activate_periodic_update_timer()

        while True:
            # Waiting for I/O
            events = self.selector.select()
            for key, mask in events:
                if mask & selectors.EVENT_READ != 0:
                    for connection in self.connections:
                        if connection.input_socket == key.fileobj:
                            data = connection.receive_routing_table_entries_from_neighbor()

                            self.lock.acquire()
                            self.update_routing_table(data)
                            self.lock.release()
    
                if mask & selectors.EVENT_WRITE != 0:
                    for connection in self.connections:
                        if connection.output_socket == key.fileobj:
                            
                            # Make sure the data not to be changed during the process of sending
                            self.lock.acquire()
                            connection.send_routing_table_entries_to_neighbor(self.routes)
                            self.lock.release()

                            # Unregister to avoid triggering infinate loop
                            self.selector.unregister(connection.output_socket)

                            self.activate_periodic_update_timer()


    def print_routing_table(self):
        """
        Print all the routing table entries on console
        """
        line = "\n---------------- Router {} Routing Table ----------------------\n".format(self.id)
        for route in self.routes:
            line += str(route)
        line += "----------------------------------------------------------------\n"
        print(line)


    def is_valid_router_id(self, router_id):
        """
        Check whether the given router id is valid
        """
        return router_id <= 64000 and router_id > 0


    def is_valid_metric(self, metric):
        """
        Check whether the given metric is valid
        """
        return metric >= 1 and metric <= INFINITE_METRIC


    def is_neighbor(self, router_id):
        """
        Check whether the given router id is one of current router's neighbors
        """
        for connection in self.connections:
            if connection.neighbor_router_id == router_id:
                return True
        return False


    def get_metric_to_neighbor(self, neighbor_router_id):
        """
        Get the metric between sending router and its neighbor
        This value is got from configuration file
        """
        for index in range(len(self.outputs)):
            neightbor = self.outputs[index][2]
            if neightbor == neighbor_router_id:
                return self.outputs[index][1]
        return None


    def get_route_destinating_to(self, dest):
        """
        Get a specified route from current routing table
        """
        result = None
        for route in self.routes:
            if route.dest == dest:
                result = route
                break
        
        return result


    def reset_timeout_timer(self, neighbor_id, destination_id):
        """
        Reset timeout timer of current route
        """
        for route in self.routes:
            if route.neighbor == neighbor_id and route.dest == destination_id:
                route.activate_timeout_timer(self.timeout_timer_callback)

                # If the garbage-collection timer is running for this route, stop it
                self.invalidate_garbage_collection_timer(neighbor_id, destination_id)
                break

    
    def add_new_route(self, neighbor, destination, metric):
        """
        Add a new route into routing table.
        Note: Should a new route to this network be established while the garbage-collection timer is running, 
        the new route will replace the one that is about to be deleted. In this case the garbage-collection timer must be cleared.
        """
        self.invalidate_garbage_collection_timer(neighbor, destination)

        new_route = Route(self.id, destination, neighbor, metric)
        new_route.activate_timeout_timer(self.timeout_timer_callback)
        self.routes.append(new_route)


    def invalidate_garbage_collection_timer(self, neighbor_id, destination_id):
        """
        Invalid the given garbage collection timer
        """
        for i in range(len(self.garbage_collection_timers)):
            timer, neighbor, destination = self.garbage_collection_timers[i]
            if neighbor == neighbor_id and destination == destination_id:
                timer.cancel()
                self.garbage_collection_timers.remove((timer, neighbor, destination))
                break


    def update_routing_table(self, routes):
        """
        Update routring table entries.
        If there is new route, add it.
        If the existed metric can be updated, update it.
        """
        for route in routes:
            # Firstly, we need to validate the correctness of entries
            if not self.is_neighbor(route.src):
                print("update_routing_table: The entry does not come from its directly-connected neighbor!")
                print("wrong route:", str(route))
                continue

            if not self.is_valid_router_id(route.neighbor):
                print("update_routing_table: wrong neighbor router id")
                print("wrong route:", str(route))
                continue

            if not self.is_valid_router_id(route.dest):
                print("update_routing_table: wrong destinated router id")
                print("wrong route:", str(route))
                continue

            if not self.is_valid_metric(route.metric):
                print("update_routing_table: wrong metric value")
                print("wrong route:", str(route))
                continue

            if route.dest == self.id:
                if route.neighbor == self.id:
                    # If the message comes from its directly-connected neighbor and the destination is to itself, there will be two situations.
                    # 1. It is a periodic message from its neighbor and the neighor is alive
                    # 2. It is a periodic message from its neighbor and the neighor has just been rebooted after crashing
                    # What we need to do is to check whether current routing table contains an entry of this route.
                    # If current routing table contains this route, reactivate the timeout timer of this route.
                    # If current routing table does not contain this route, add this route into routing table.
                    route_in_routing_table = self.get_route_destinating_to(route.src)
                    if route_in_routing_table == None:
                         self.add_new_route(route.src, route.src, route.metric)
                    else:
                        if route_in_routing_table.neighbor == route.src:
                            if route.metric != INFINITE_METRIC:
                                route_in_routing_table.metric = route.metric
                                self.reset_timeout_timer(route.src, route.src)
                        else:
                            if route.metric < route_in_routing_table.metric:
                                route_in_routing_table.neighbor = route.src
                                route_in_routing_table.metric = route.metric
                                self.reset_timeout_timer(route.src, route.dest)
                continue

            # Calculate the total metric to destination via neighbor router
            metric_to_neighbor = self.get_metric_to_neighbor(route.src)
            metric = min(metric_to_neighbor + route.metric, INFINITE_METRIC)

            # Secondly, process the valid RTEs one by one
            route_in_routing_table = self.get_route_destinating_to(route.dest)
            if route_in_routing_table == None:
                # Add a new routing entry in routing table
                if metric != INFINITE_METRIC:
                    # There is no point in adding a route which is unusable
                    self.add_new_route(route.src, route.dest, metric)
            else:
                # Check whether to update an existing entry
                if route_in_routing_table.neighbor == route.src:
                    # This datagram is from the same router as the existing route.
                    # Check whether current metric is already 16. If so, ignore this route to avoid sending 
                    # multitime triggered updates
                    if route_in_routing_table.metric != INFINITE_METRIC:
                        route_in_routing_table.metric = metric
                        if metric == INFINITE_METRIC:
                            self.activate_triggered_updates_timer()
                            self.activate_garbage_collection_timer(route_in_routing_table.neighbor, route_in_routing_table.dest)
                        else:
                            self.reset_timeout_timer(route.src, route.dest)
                else:
                    # The datagram is from the other router as the existing route
                    if metric < route_in_routing_table.metric:
                        route_in_routing_table.neighbor = route.src
                        route_in_routing_table.metric = metric
                        self.reset_timeout_timer(route.src, route.dest)

        self.print_routing_table()


    def activate_periodic_update_timer(self):
        """
        This function will initialise a timer to handle the process of periodic updates.
        Accordind to the specification of the assignment 1, it is better to set a timer with a random interval 
        between 0.8 * period and 1.2 * period.
        """
        if self.periodic_update_timer != None:
            self.periodic_update_timer.cancel()
    
        self.periodic_update_timer = threading.Timer(PERIODIC_UPDATE_TIMER_INTERVAL * random.uniform(0.8, 1.2), self.periodic_update_timer_callback)
        self.periodic_update_timer.start()


    def activate_triggered_updates_timer(self):
        """
        This function will initialise a timer to handle the process of triggered updates
        Accordind to RIP, it is better to set a timer with a random interval.
        """
        timer = threading.Timer(random.uniform(0, 2), self.triggered_update_timer_callback)
        self.triggered_update_timers.append(timer)
        timer.start()


    def activate_garbage_collection_timer(self, neighbor, destination):
        """
        This function will initialise a timer to handle the process of garbage collection
        """
        # Note that the deletion process is started only when the metric is first set to infinity. 
        # If the metric was already infinity, then a new deletion process is not started.

        for timer, n, d in self.garbage_collection_timers:
            if n == neighbor and d == destination:
                return

        timer = threading.Timer(GARBAGE_COLLECTION_TIMER_INTERVAL, self.garbage_collection_timer_callback, [neighbor, destination])
        self.garbage_collection_timers.append((timer, neighbor, destination))
        timer.start()


    def register_write_event(self):
        """
        This function is triggered by periodic update timer or triggered update time.
        After registration, current route will send entire routing table to its neighbors
        """
        for connection in self.connections:
            self.selector.register(connection.output_socket, selectors.EVENT_WRITE)


    # Timer callbacks
    def periodic_update_timer_callback(self):
        """
        Send periodic update messages to the neighbor router.
        This function just register a write event into selector, not send messages immediately
        This event will trigger while-loop to perform the operation of sending messages
        """
        self.register_write_event()


    def triggered_update_timer_callback(self):
        """
        This function is triggered by a triggered update timer.
        This function is used to nofity neighbors that invalid routes occur。
        According to the specification of assignment, RIP response packets always include the entire routing table.
        """
        self.register_write_event()


    def timeout_timer_callback(self, neighbor, destination):
        """
        This function is triggered by a connection timeout and launch the garbage collection timer.
        """
        self.lock.acquire()
        for route in self.routes:
            if route.neighbor == neighbor and route.dest == destination:
                route.metric = INFINITE_METRIC
        self.lock.release()

        self.activate_triggered_updates_timer()
        self.activate_garbage_collection_timer(neighbor, destination)


    def garbage_collection_timer_callback(self, neighbor, destination):
        """
        This function is triggered by a garbage collection timer.
        Remove the invalid route in routing table and self.connections
        """
        valid_routes = []

        # Remove the invalid route form self.routes
        self.lock.acquire()

        self.print_routing_table()
        for route in self.routes:
            if not (route.neighbor == neighbor and route.dest == destination):
                valid_routes.append(route)

        self.routes = valid_routes
        self.print_routing_table()

        self.lock.release()


def main():
    """
    Create a rip daemon and run it
    """
    if len(sys.argv) != 2:
        print("Need specify a config file!")
        return

    filename = sys.argv[1]
    rip_daemon = RIPDaemon(filename)
    rip_daemon.activate()


if __name__ == "__main__":
    main()
    