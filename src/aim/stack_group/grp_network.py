from aim.stack_group import StackEnum, StackOrder, Stack, StackGroup, StackTags
from aim import models
from aim.models import schemas
from pprint import pprint
import aim.cftemplates
from aim import utils

class NetworkStackGroup(StackGroup):
    def __init__(self, aim_ctx, account_ctx, env_ctx, stack_tags):

        super().__init__(aim_ctx,
                         account_ctx,
                         env_ctx.netenv_id,
                         "Net",
                         env_ctx)

        self.env_ctx = env_ctx
        self.config_ref_prefix = self.env_ctx.config_ref_prefix
        self.region = self.env_ctx.region
        self.stack_tags = stack_tags

    def log_init_status(self, name, is_enabled):
        "Logs the init status of a network component"
        utils.log_action_col('Init', 'Network', name, '', enabled=is_enabled)

    def init(self):
        # Network Stack Templates
        # VPC Stack
        vpc_config = self.env_ctx.vpc_config()
        self.log_init_status('VPC', vpc_config.is_enabled())
        vpc_config_ref = '.'.join([self.config_ref_prefix, "network.vpc"])
        vpc_config.resolve_ref_obj = self
        vpc_config.private_hosted_zone.resolve_ref_obj = self
        vpc_template = aim.cftemplates.VPC(self.aim_ctx,
                                           self.account_ctx,
                                           self.region,
                                           self, # stack_group
                                           StackTags(self.stack_tags),
                                           vpc_config,
                                           vpc_config_ref)
        self.vpc_stack = vpc_template.stack

        # Segments
        self.segment_list = []
        self.segment_dict = {}
        for segment_id in self.env_ctx.segment_ids():
            segment_config = self.env_ctx.segment_config(segment_id)
            self.log_init_status('Segment: {}'.format(segment_id), segment_config.is_enabled())
            segment_config.resolve_ref_obj = self
            segment_config_ref = '.'.join([self.config_ref_prefix, "network.vpc.segments", segment_id])
            segment_template = aim.cftemplates.Segment(self.aim_ctx,
                                                       self.account_ctx,
                                                       self.region,
                                                       self, # stack_group
                                                       StackTags(self.stack_tags),
                                                       [StackOrder.PROVISION], # stack_order
                                                       self.env_ctx,
                                                       segment_id,
                                                       segment_config,
                                                       segment_config_ref)
            segment_stack = segment_template.stack
            self.segment_dict[segment_id] = segment_stack
            self.segment_list.append(segment_stack)

        # Security Groups
        sg_config = self.env_ctx.security_groups()
        self.sg_list = []
        self.sg_dict = {}
        for sg_id in sg_config:
            # Set resolve_ref_obj
            for sg_obj_id in sg_config[sg_id]:
                sg_config[sg_id][sg_obj_id].resolve_ref_obj = self
                self.log_init_status(
                    'Security Group: {}.{}'.format(sg_id, sg_obj_id),
                    sg_config[sg_id][sg_obj_id].is_enabled()
                )
            sg_group_config_ref = '.'.join([self.config_ref_prefix, "network.vpc.security_groups", sg_id])
            sg_template = aim.cftemplates.SecurityGroups( aim_ctx=self.aim_ctx,
                                                          account_ctx=self.account_ctx,
                                                          aws_region=self.region,
                                                          stack_group=self,
                                                          stack_tags=StackTags(self.stack_tags),
                                                          env_ctx=self.env_ctx,
                                                          security_groups_config=sg_config[sg_id],
                                                          sg_group_id=sg_id,
                                                          sg_group_config_ref=sg_group_config_ref )
            sg_stack = sg_template.stack
            self.sg_list.append(sg_stack)
            self.sg_dict[sg_id] = sg_stack

        # Wait for Segment Stacks
        for segment_stack in self.segment_list:
            self.add_stack_order(segment_stack, [StackOrder.WAIT])

        # VPC Peering Stack
        if vpc_config.peering != None:
            peering_config = self.env_ctx.peering_config()
            peering_config_ref = '.'.join([self.config_ref_prefix, "network.vpc.peering"])
            for peer_id in peering_config.keys():
                peer_config = vpc_config.peering[peer_id]
                peer_config.resolve_ref_obj = self
                self.log_init_status('VPC Peer: {}'.format(peer_id), peer_config.is_enabled())

            peering_template = aim.cftemplates.VPCPeering(
                self.aim_ctx,
                self.account_ctx,
                self.region,
                self, # stack_order
                StackTags(self.stack_tags),
                self.env_ctx.netenv_id,
                self.env_ctx.config.network,
                peering_config_ref
            )
            self.peering_stack = peering_template.stack

        # NAT Gateway
        self.nat_list = []
        for nat_id in vpc_config.nat_gateway.keys():
            nat_config = vpc_config.nat_gateway[nat_id]
            self.log_init_status('NAT Gateway: {}'.format(nat_id), nat_config.is_enabled())
            # We now disable the NAT Gatewy in the template so that we can delete it and recreate
            # it when disabled.
            nat_template = aim.cftemplates.NATGateway( aim_ctx=self.aim_ctx,
                                                       account_ctx=self.account_ctx,
                                                       aws_region=self.region,
                                                       stack_group=self,
                                                       stack_tags=StackTags(self.stack_tags),
                                                       stack_order=[StackOrder.PROVISION],
                                                       nat_config=nat_config)
            nat_stack = nat_template.stack
            self.nat_list.append(nat_stack)

        for nat_stack in self.nat_list:
            self.add_stack_order(nat_stack, [StackOrder.WAIT])

        utils.log_action_col('Init', 'Network', 'Completed', enabled=self.env_ctx.config.network.is_enabled())

    def get_vpc_stack(self):
        return self.vpc_stack


    def get_security_group_stack(self, sg_id):
        return self.sg_dict[sg_id]

    def get_segment_stack(self, segment_id):
        return self.segment_dict[segment_id]

    def resolve_ref(self, ref):
        if ref.raw.endswith('network.vpc.id'):
            return self.vpc_stack
        if schemas.IPrivateHostedZone.providedBy(ref.resource):
            return self.vpc_stack
        if ref.raw.find('network.vpc.segments') != -1:
            segment_id = ref.next_part('network.vpc.segments')
            return self.get_segment_stack(segment_id)
        if schemas.ISecurityGroup.providedBy(ref.resource):
            if ref.resource_ref == 'id':
                sg_id = ref.parts[-3]
                return self.get_security_group_stack(sg_id)


    def validate(self):
        # Generate Stacks
        # VPC Stack
        super().validate()

    def provision(self):
        # self.validate()
        super().provision()
