import eventlet

eventlet.monkey_patch()

import sys
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.services.protocols.bgp.bgpspeaker import BGPSpeaker


class FinalDynamicController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(FinalDynamicController, self).__init__(*args, **kwargs)
        self.datapaths = {}
        self.access_dpid = None
        self.port_maps = {}
        self.learned_routes = {}

        self.speaker = BGPSpeaker(as_number=200,
                                  router_id='3.3.3.3',
                                  best_path_change_handler=self.on_route_change)

        self.speaker.neighbor_add(address='192.168.60.2', remote_as=100)
        self.speaker.prefix_add(prefix='200.1.1.0/24')
        print("\n[SYSTEM] BGP Speaker initialized. Re-Sync logic active.")


    def on_route_change(self, event):
        if event.is_withdraw:
            self.learned_routes.pop(event.prefix, None)
            return

        # 1. Update Memory
        self.learned_routes[event.prefix] = event.nexthop

        # 2. Print the formatted RIB Table
        print "\n" + "=" * 50
        print "      SDN BGP ROUTING TABLE (RIB) UPDATE"
        print "      Active Switches: {}".format(len(self.datapaths))
        print "-" * 50
        print "{:<22} | {:<18}".format('Network Prefix', 'Next Hop Address')
        print "-" * 50
        for prefix, nexthop in self.learned_routes.items():
            print "{:<22} | {:<18}".format(prefix, nexthop)
        print "-" * 50
        print "[ORCHESTRATION] BGP Update: {} via {}".format(event.prefix, event.nexthop)
        print "=" * 50 + "\n"
        sys.stdout.flush()