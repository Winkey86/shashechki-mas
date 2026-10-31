"""Маршрут: минимальное время, длина, лексикографический путь."""
import heapq
class Router:
    def __init__(self,city):
        self.nodes={x['id']:x for x in city['nodes']};self.edges={e['id']:e for e in city['edges']};self.adj={n:[] for n in self.nodes};self.cache={}
        for e in city['edges']:self.adj[e['from']].append(e)
    def route(self,origin,destination):
        key=(origin,destination)
        if key in self.cache:return self.cache[key]
        q=[(0,0,(),origin)];best={}
        while q:
            ms,m,path,node=heapq.heappop(q)
            if node in best:continue
            best[node]=(ms,m,path)
            if node==destination:
                result={'edge_ids':list(path),'distance_m':m,'travel_ms':ms,'origin':origin,'destination':destination};self.cache[key]=result;return result
            for e in self.adj.get(node,[]):
                if e['to'] not in best:heapq.heappush(q,(ms+e['travel_ms'],m+e['distance_m'],path+(e['id'],),e['to']))
        self.cache[key]=None;return None
    def position(self,movement,time_ms):
        elapsed=max(0,min(time_ms-movement['from_ms'],movement['to_ms']-movement['from_ms']))
        route=movement['route'];node=route['origin']
        for edge_id in route['edge_ids']:
            e=self.edges[edge_id]
            if elapsed<=e['travel_ms']:
                a,b=self.nodes[e['from']],self.nodes[e['to']];f=elapsed/e['travel_ms']
                return {'x':a['x']+(b['x']-a['x'])*f,'y':a['y']+(b['y']-a['y'])*f}
            elapsed-=e['travel_ms'];node=e['to']
        return {k:self.nodes[node][k] for k in ('x','y')}
