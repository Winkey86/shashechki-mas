import unittest,copy
from shashechki.validation import load
from shashechki.protocol import simulate
class ProjectionTests(unittest.TestCase):
    def test_checkpoints_reconstruct_state(self):
        r=simulate(load('scenarios/conflict.json'));data=r.playback;state=copy.deepcopy(data['initial_snapshot']);cp={c['change_index']:c for c in data['checkpoints']}
        for index,change in enumerate(data['changes'],1):
            for key,items in change['assignments'].items():
                if key in {'drivers','passengers','orders','dispatcher_telemetry'}:state[key].update(copy.deepcopy(items))
                else:state[key]=copy.deepcopy(items)
            if index in cp:self.assertEqual(state,cp[index]['state'])
        self.assertEqual(state['orders']['O000']['state'],'completed')
    def test_frozen_price_source(self):
        s=load('scenarios/conflict.json');s['config']['rating_policy']='dynamic';r=simulate(s)
        snapshots=[c['assignments']['orders']['O000'] for c in r.playback['changes'] if 'O000' in c['assignments'].get('orders',{})]
        self.assertEqual(snapshots[0]['pricing'],snapshots[-1]['pricing'])
