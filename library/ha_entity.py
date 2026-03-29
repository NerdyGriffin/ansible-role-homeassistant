#!/usr/bin/python
# -*- coding: utf-8 -*-

"""Ansible module for managing Home Assistant entities."""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: ha_entity
short_description: Manage Home Assistant entities via WebSocket API
description:
  - List, get, update, and reset Home Assistant entity registry entries.
  - Runs on the Ansible controller (connection local).
options:
  homeassistant:
    description: Connection parameters for Home Assistant.
    required: true
    type: dict
    suboptions:
      host:
        description: Home Assistant hostname or IP.
        required: true
        type: str
      port:
        description: Home Assistant API port.
        type: int
        default: 8123
      access_token:
        description: Long-lived access token.
        required: true
        type: str
      tls:
        description: Use TLS for connections.
        type: bool
        default: false
      ssl_verify:
        description: Verify SSL certificates.
        type: bool
        default: false
  action:
    description: Action to perform.
    required: true
    type: str
    choices: ['list', 'get', 'update', 'reset_name']
  entity_id:
    description: Entity ID (required for get/update/reset_name).
    type: str
  search:
    description: Regex to filter entities (for list action).
    type: str
  name:
    description: New friendly name (for update action). Set to null to reset.
    type: str
  new_entity_id:
    description: New entity ID to rename to (for update action).
    type: str
author:
  - NerdyGriffin
'''

EXAMPLES = r'''
- name: List all sensor entities
  ha_entity:
    homeassistant: "{{ homeassistant }}"
    action: list
    search: "^sensor\\."

- name: Get an entity's registry entry
  ha_entity:
    homeassistant: "{{ homeassistant }}"
    action: get
    entity_id: sensor.garage_motion_sensor_rssi

- name: Rename an entity
  ha_entity:
    homeassistant: "{{ homeassistant }}"
    action: update
    entity_id: sensor.old_name
    new_entity_id: sensor.new_name

- name: Reset an entity's friendly name to default
  ha_entity:
    homeassistant: "{{ homeassistant }}"
    action: reset_name
    entity_id: sensor.garage_motion_sensor_rssi
'''

RETURN = r'''
entities:
  description: List of entities (for list action).
  returned: when action is list
  type: list
  elements: dict
entity:
  description: Entity registry entry (for get/update/reset_name).
  returned: when action is get, update, or reset_name
  type: dict
'''

import re

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.ha_client import HomeAssistantClient, check_dependencies


def run_module():
    module_args = dict(
        homeassistant=dict(type='dict', required=True, no_log=False, options=dict(
            host=dict(type='str', required=True),
            port=dict(type='int', default=8123),
            access_token=dict(type='str', required=True, no_log=True),
            tls=dict(type='bool', default=False),
            ssl_verify=dict(type='bool', default=False),
        )),
        action=dict(type='str', required=True, choices=['list', 'get', 'update', 'reset_name']),
        entity_id=dict(type='str'),
        search=dict(type='str'),
        name=dict(type='str'),
        new_entity_id=dict(type='str'),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        required_if=[
            ('action', 'get', ['entity_id']),
            ('action', 'update', ['entity_id']),
            ('action', 'reset_name', ['entity_id']),
        ],
        supports_check_mode=True,
    )

    missing = check_dependencies()
    if missing:
        module.fail_json(msg="Missing Python dependencies: {deps}".format(
            deps=", ".join(missing)
        ))

    result = dict(changed=False)

    try:
        client = HomeAssistantClient.from_ansible_params(module.params['homeassistant'])

        with client:
            action = module.params['action']

            if action == 'list':
                entities = client.list_entities(
                    search_regex=module.params.get('search')
                )
                result['entities'] = [
                    {
                        'entity_id': e.get('entity_id'),
                        'name': e.get('name'),
                        'original_name': e.get('original_name'),
                        'platform': e.get('platform'),
                        'device_id': e.get('device_id'),
                        'disabled_by': e.get('disabled_by'),
                    }
                    for e in entities
                ]

            elif action == 'get':
                entity = client.get_entity(module.params['entity_id'])
                result['entity'] = entity

            elif action == 'update':
                entity_id = module.params['entity_id']
                current = client.get_entity(entity_id)

                update_kwargs = {}
                if module.params.get('name') is not None:
                    if current.get('name') != module.params['name']:
                        update_kwargs['name'] = module.params['name']
                if module.params.get('new_entity_id'):
                    if entity_id != module.params['new_entity_id']:
                        update_kwargs['new_entity_id'] = module.params['new_entity_id']

                if update_kwargs:
                    result['changed'] = True
                    if not module.check_mode:
                        updated = client.update_entity(entity_id, **update_kwargs)
                        result['entity'] = updated
                    else:
                        result['entity'] = current
                else:
                    result['entity'] = current

            elif action == 'reset_name':
                entity_id = module.params['entity_id']
                current = client.get_entity(entity_id)

                if current.get('name') is not None:
                    result['changed'] = True
                    if not module.check_mode:
                        updated = client.update_entity(entity_id, name=None)
                        result['entity'] = updated
                    else:
                        result['entity'] = current
                else:
                    result['entity'] = current

    except Exception as e:
        module.fail_json(msg=str(e), **result)

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
