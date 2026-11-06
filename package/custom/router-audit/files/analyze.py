#!/usr/bin/python3
"""Generate a small evidence packet from the puller's SQLite database."""
import argparse,json,sqlite3,datetime,collections,math
p=argparse.ArgumentParser();p.add_argument('database');p.add_argument('--hours',type=int,default=1);a=p.parse_args()
db=sqlite3.connect('file:'+a.database+'?mode=ro',uri=True)
start=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(hours=a.hours)).isoformat()
records=[json.loads(r[0]) for r in db.execute('select payload from batches where time>=? order by time',(start,))]
facts=[];triggers=[];events=[];changes=[]
dns=[]
for r in records:
    d=r['data'];m=r['module']
    if m=='system':
        mem=d['memory_bytes'];avail=mem.get('MemAvailable',0)/max(mem.get('MemTotal',1),1)
        if avail<0.1:triggers.append({'rule':'low_available_memory','time':r['collected_at'],'available_ratio':avail})
    elif m=='services':
        for svc in d.get('procd',[]):
            if not svc.get('running',True):triggers.append({'rule':'service_not_running','time':r['collected_at'],'service':svc['service']})
        if d.get('failed'):triggers.append({'rule':'systemd_failed','time':r['collected_at'],'units':d['failed'][:2000]})
    elif m=='network':
        for probe in d.get('probes',[]):
            if not probe['ok']:triggers.append({'rule':'probe_failed','time':r['collected_at'],'target':probe['target'],'path':probe['path']})
    elif m=='events':events+=d.get('events',[])
    elif m=='changes':changes+=d.get('revisions',[])
    elif m=='dns_queries':dns+=d.get('events',[])
client_dns={}
for e in dns:
    if e['client'] in ['127.0.0.1','::1'] or e['client'].startswith(('127.0.0.1:','[::1]:')):continue
    key=(e['source'],e['client']);client_dns.setdefault(key,[]).append(e)
for (source,client),rows in client_dns.items():
    known=[e for e in rows if e.get('rcode') is not None];bad=sum(e['rcode'] in [2,3] for e in known)
    if len(known)>=30 and bad/len(known)>.2:triggers.append({'rule':'dns_error_ratio','source':source,'client':client,'ratio':bad/len(known),'observations':len(known)})
    suspicious=[]
    for e in rows:
        label=max(e['qname'].split('.'),key=len);counts=collections.Counter(label)
        entropy=-sum((n/len(label))*math.log2(n/len(label)) for n in counts.values()) if label else 0
        if len(label)>40 and entropy>3.5:suspicious.append(e['qname'])
    if len(set(suspicious))>20:triggers.append({'rule':'dns_unusual_labels_candidate','source':source,'client':client,'unique_names':len(set(suspicious))})
unique=lambda rows:list({json.dumps(x,sort_keys=True):x for x in rows}.values())
packet={'schema_version':'1.0','start':start,'end':datetime.datetime.now(datetime.timezone.utc).isoformat(),'triggers':triggers[-30:],'verified_facts':facts,'hypotheses':[],'related_changes':unique(changes)[-10:],'log_evidence':unique(events)[-30:],'baseline':{'valid':False,'reason':'First version uses absolute rules only'},'coverage_gaps':['Client encrypted DNS unobserved','Container runtime health not collected','No full connection accounting'],'available_tools':['system','network','services','firewall','changes','incidents']}
print(json.dumps(packet,indent=2))
