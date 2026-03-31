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

        self.speaker = BGPSpeaker(as_number=500, 
                                 router_id='10.20.1.1',
                                 best_path_change_handler=self.on_route_change)

        self.speaker.neighbor_add(address='10.20.1.2', remote_as=300) 
        self.speaker.neighbor_add(address='10.45.1.2', remote_as=400) 
        self.speaker.prefix_add(prefix='200.1.1.0/24')
        print("\n[SYSTEM] BGP Speaker initialized. Re-Sync logic active.")

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        self.datapaths[datapath.id] = datapath
        parser = datapath.ofproto_parser
        req = parser.OFPPortDescStatsRequest(datapath, 0)
        datapath.send_msg(req)

    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, MAIN_DISPATCHER)
    def port_desc_stats_reply_handler(self, ev):
        datapath = ev.msg.datapath
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        
        self.port_maps[datapath.id] = {p.name.decode(): p.port_no for p in ev.msg.body}
        current_map = self.port_maps[datapath.id]
        
        self.del_flows(datapath)
        is_access = any("sw3-eth" in name for name in current_map.keys())

        if is_access:
            self.access_dpid = datapath.id
            p_no = current_map.get("sw3-eth1")
            print(f"[DISCOVERY] SW3 (Access) ID: {datapath.id}")
            if p_no:
                self.add_flow(datapath, 1000, parser.OFPMatch(eth_type=0x0800, ipv4_dst='200.1.1.1'), [parser.OFPActionOutput(p_no)])
                self.add_flow(datapath, 1000, parser.OFPMatch(eth_type=0x0806), [parser.OFPActionOutput(ofproto.OFPP_FLOOD)])
        else:
            print(f"[DISCOVERY] Edge Switch ID: {datapath.id}")
            phys_port = "eno1" if "eno1" in current_map else "eno3"
            patch_port = next((n for n in current_map.keys() if "-sw3" in n), None)
            
            p_no = current_map.get(phys_port)
            pt_no = current_map.get(patch_port)

            if p_no:
                self.add_flow(datapath, 3000, parser.OFPMatch(eth_type=0x0800, ip_proto=6, tcp_src=179, in_port=p_no), [parser.OFPActionOutput(ofproto.OFPP_LOCAL)])
                self.add_flow(datapath, 3000, parser.OFPMatch(eth_type=0x0800, ip_proto=6, tcp_dst=179, in_port=p_no), [parser.OFPActionOutput(ofproto.OFPP_LOCAL)])
                self.add_flow(datapath, 3000, parser.OFPMatch(in_port=ofproto.OFPP_LOCAL), [parser.OFPActionOutput(p_no)])

                if pt_no:
                    self.add_flow(datapath, 2500, parser.OFPMatch(eth_type=0x0800, in_port=p_no, ipv4_dst='200.1.1.0/24'), [parser.OFPActionOutput(pt_no)])
            
            self.add_flow(datapath, 1000, parser.OFPMatch(eth_type=0x0806), [parser.OFPActionOutput(ofproto.OFPP_NORMAL)])

        # RE-SYNC: Catch up on BGP routes learned while switch was offline
        for prefix, nexthop in self.learned_routes.items():
            self._program_route(datapath, prefix, nexthop)

        self.add_flow(datapath, 0, parser.OFPMatch(), [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER)])

    def on_route_change(self, event):
        if event.is_withdraw:
            self.learned_routes.pop(event.prefix, None)
            return

        # 1. Update Memory
        self.learned_routes[event.prefix] = event.nexthop
        
        # 2. Print the formatted RIB Table
        print("\n" + "="*50)
        print("      SDN BGP ROUTING TABLE (RIB) UPDATE")
        print(f"      Active Switches: {len(self.datapaths)}")
        print("-" * 50)
        print(f"{'Network Prefix':<22} | {'Next Hop Address':<18}")
        print("-" * 50)
        for prefix, nexthop in self.learned_routes.items():
            print(f"{prefix:<22} | {nexthop:<18}")
        print("-" * 50)
        print(f"[ORCHESTRATION] BGP Update: {event.prefix} via {event.nexthop}")

        # 3. Choose Best Routes and Program flows
        for dpid, dp in self.datapaths.items():
            self._program_route(dp, event.prefix, event.nexthop)
        
        print("="*50 + "\n")
        sys.stdout.flush()

    def _program_route(self, dp, prefix, nexthop):
        parser = dp.ofproto_parser
        cmap = self.port_maps.get(dp.id, {})
        if not cmap: return

        if dp.id == self.access_dpid:
            # Logic: Choose patch based on BGP Nexthop
            target = "sw3-sw1" if nexthop == '10.20.1.2' else "sw3-sw2"
            p_no = cmap.get(target)
            if p_no:
                self.add_flow(dp, 500, parser.OFPMatch(eth_type=0x0800, ipv4_dst=prefix), [parser.OFPActionOutput(p_no)])
                print(f"  -> Rule Pushed to SW3: {prefix} out via {target}")
        else:
            # RETURN PATH on Edge Switches
            phys_port = "eno1" if "eno1" in cmap else "eno3"
            p_no = cmap.get(phys_port)
            patch_no = next((v for k, v in cmap.items() if "-sw3" in k), None)
            if p_no and patch_no:
                self.add_flow(dp, 500, parser.OFPMatch(eth_type=0x0800, in_port=patch_no, ipv4_dst=prefix), [parser.OFPActionOutput(p_no)])
                print(f"  -> Rule Pushed to Edge {dp.id}: {prefix} out via {phys_port}")

    def add_flow(self, datapath, priority, match, actions):
        inst = [datapath.ofproto_parser.OFPInstructionActions(datapath.ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = datapath.ofproto_parser.OFPFlowMod(datapath=datapath, priority=priority, match=match, instructions=inst)
        datapath.send_msg(mod)

    def del_flows(self, datapath):
        mod = datapath.ofproto_parser.OFPFlowMod(datapath=datapath, command=datapath.ofproto.OFPFC_DELETE,
                                                out_port=datapath.ofproto.OFPP_ANY, out_group=datapath.ofproto.OFPG_ANY,
                                                match=datapath.ofproto_parser.OFPMatch())
        datapath.send_msg(mod)