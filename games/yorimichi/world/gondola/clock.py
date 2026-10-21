"""One periodic arc-length clock for the fitted, detachable-grip cabin circuit.

Positions stay on the audited polyline. Constant acceleration within each small
arc interval reaches zero speed at the four platform berths. Dwell never moves
an open door; station approach limits and braking use the same cyclic table.
"""
import bisect
import math

DWELL=12.
ACCEL=.35
LINE_SPEED=5.
STATION_SPEED=.6


def distance(a,b):
    return math.sqrt(sum((x-y)**2 for x,y in zip(a,b)))


def interpolate(a,b,t):
    return [x+(y-x)*t for x,y in zip(a,b)]


def arc_lengths(points):
    result=[0.]
    for a,b in zip(points,points[1:]):
        length=distance(a,b)
        if not math.isfinite(length) or length<1e-8:
            raise ValueError('Cabin circuit has an invalid or duplicate segment')
        result.append(result[-1]+length)
    if len(points)<4 or distance(points[0],points[-1])>1e-6:
        raise ValueError('Cabin circuit must close exactly')
    return result


def point_at(points,arc,s):
    s%=arc[-1]
    i=min(len(points)-2,bisect.bisect_right(arc,s)-1)
    return interpolate(points[i],points[i+1],(s-arc[i])/(arc[i+1]-arc[i]))


def prepare(points,stations,towers=()):
    """Build a periodic clock from the already fitted kit-loop/rope circuit.

    Stations carry origin/along/lateral/platform_z and their exact berth targets.
    No second spatial path is authored here. A target must already be on this
    circuit within the same centimetre tolerance as the station's physical fit.
    """
    points=[list(map(float,p)) for p in points]
    # Insert the four berth coordinates onto their existing straight polyline
    # segments. This refines the representation without moving the fitted path.
    for station in stations:
        for side in (-1,1):
            target=[station['origin'][k]+station['berth_x']*station['along'][k]+
                    station['gauge']/2*side*station['lateral'][k] for k in (0,1)]+[station['rope_z']]
            best=None
            for i,(a,b) in enumerate(zip(points,points[1:])):
                ab=[v-u for u,v in zip(a,b)];length2=sum(v*v for v in ab)
                t=max(0.,min(1.,sum((q-u)*v for q,u,v in zip(target,a,ab))/length2))
                q=interpolate(a,b,t);candidate=(distance(q,target),i,t,q)
                if best is None or candidate[0]<best[0]:best=candidate
            error,i,t,q=best
            if error>1e-6:raise ValueError('Audited circuit misses a platform berth')
            if 1e-8<t<1-1e-8:points.insert(i+1,q)
    arc=arc_lengths(points)
    stop_indices={};stop_stations={};station_nodes=set()
    for station in stations:
        origin,along,lateral=station['origin'],station['along'],station['lateral']
        for i,p in enumerate(points[:-1]):
            q=[p[k]-origin[k] for k in (0,1)]
            x=sum(q[k]*along[k] for k in (0,1));y=sum(q[k]*lateral[k] for k in (0,1))
            if x<=station['mouth_x']+.61 and abs(y)<=station['gauge']/2+.01 and abs(p[2]-station['rope_z'])<.01:
                station_nodes.add(i)
        for side in (-1,1):
            target=[origin[k]+station['berth_x']*along[k]+station['gauge']/2*side*lateral[k] for k in (0,1)]+[station['rope_z']]
            index=min(range(len(points)-1),key=lambda i:distance(points[i],target))
            if distance(points[index],target)>.011:
                raise ValueError('Audited circuit misses a platform berth')
            stop_indices[index]=station['id'];stop_stations[index]=side
    if len(stop_indices)!=4:
        raise ValueError('Two terminals must supply four distinct platform berths')
    speed=[STATION_SPEED if i in station_nodes else LINE_SPEED for i in range(len(points)-1)]
    for i in stop_indices:speed[i]=0.
    n=len(speed)
    # Two cyclic sweeps propagate every berth's braking/acceleration constraint
    # through the entire path, including its closing interval.
    for _ in range(2):
        for i in range(n):
            j=(i+1)%n;ds=arc[i+1]-arc[i]
            speed[j]=min(speed[j],math.sqrt(speed[i]**2+2*ACCEL*ds))
        for i in range(n-1,-1,-1):
            j=(i+1)%n;ds=arc[i+1]-arc[i]
            speed[i]=min(speed[i],math.sqrt(speed[j]**2+2*ACCEL*ds))
    rows=[];time=0.;stops=[]
    for i in range(n):
        if i in stop_indices:
            stops.append({'start':time,'end':time+DWELL,'station':stop_indices[i],'side':stop_stations[i],'arc':arc[i]})
            rows.append([time,time+DWELL,arc[i],arc[i],0.,0.]);time+=DWELL
        ds=arc[i+1]-arc[i];va,vb=speed[i],speed[(i+1)%n]
        if va+vb<=0:
            raise ValueError('Adjacent stopped circuit samples cannot travel')
        dt=2*ds/(va+vb)
        rows.append([time,time+dt,arc[i],arc[i+1],va,(vb-va)/dt]);time+=dt
    events=[]
    for station in stations:
        # Grip release/attach occurs where the audited loop meets its line.
        indices=sorted(i for i in station_nodes if distance(points[i],station['mouth_grip'])<6.1)
        if indices:
            for i,kind in ((indices[0],'release'),(indices[-1],'attach')):
                events.append({'time':next(row[0] for row in rows if abs(row[2]-arc[i])<1e-8),'kind':kind})
    for tower in towers:
        for side in (-1,1):
            target=tower['tracks'][str(side)]
            i=min(range(n),key=lambda j:distance(points[j],target))
            events.append({'time':next(row[0] for row in rows if abs(row[2]-arc[i])<1e-8),'kind':'tower'})
    return {'cycle_s':time,'points':points,'arc':arc,'intervals':rows,'stops':stops,'events':events}


def state(clock,time):
    t=time%clock['cycle_s']
    rows=clock['intervals']
    row=rows[min(len(rows)-1,bisect.bisect_right(rows,t,key=lambda row:row[0])-1)]
    dt=t-row[0]
    s=min(row[3],max(row[2],row[2]+row[4]*dt+.5*row[5]*dt*dt))
    stop=next((i for i,v in enumerate(clock['stops']) if v['start']<=t<v['end']),-1)
    return {'arc':s,'speed':row[4]+row[5]*dt,'stop':stop,
            'point':point_at(clock['points'],clock['arc'],s)}


def spacing(clock,cabins,minimum=5.8):
    """Reject a headway whose neighbouring cabins can overlap at a station.

    Between samples relative speed is at most twice line speed. The sampled
    distance must therefore exceed the body diagonal plus that movement bound.
    Adaptive time intervals retain a conservative bound instead of assuming a
    few stationary snapshots prove the whole cycle.
    """
    if not 2<=cabins<=32 or not math.isfinite(minimum) or minimum<=0:raise ValueError('Invalid cabin roster')
    pending=[(0.,clock['cycle_s'])];best=float('inf');count=0
    headway=clock['cycle_s']/cabins
    while pending:
        a,b=pending.pop();middle=(a+b)/2
        first=state(clock,middle);second=state(clock,middle+headway)
        gap=distance(first['point'],second['point']);count+=1
        # Global speed bound applies across interval and dwell boundaries.
        bound=gap-2*LINE_SPEED*(b-a)/2
        if bound>=minimum:
            best=min(best,bound);continue
        if b-a<.002:raise ValueError('Cabin headway cannot prove body clearance')
        pending.extend(((a,middle),(middle,b)))
    return {'minimum_bound_m':best,'required_m':minimum,'intervals':count,'pass':True}
