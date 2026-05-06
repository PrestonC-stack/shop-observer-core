import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK_FILE = ROOT / "outputs" / "advisor_tasks.json"

now = datetime.now(timezone.utc)

def t(hours_ago):
    return (now - timedelta(hours=hours_ago)).isoformat()

def due(minutes_from_now):
    return (now + timedelta(minutes=minutes_from_now)).isoformat()

demo_tasks = [
    # P1 ACTION NOW
    {"ro":"20001","customer":"John Smith","vehicle":"2019 Ford F-250","owner":"Drew","risk":"CRITICAL","priority":"P1","status":"QC","task":"QC overdue. Verify repair complete and move to Advisor QC.","created_at":t(5),"due_by":due(-90),"status_tracking":"pending","overdue":True,"idle_hours":5.0},
    {"ro":"20002","customer":"Sarah Lee","vehicle":"2020 Chevy Tahoe","owner":"Mitch","risk":"RED","priority":"P1","status":"Waiting approval","task":"Customer approval follow-up needed now. Promise time is at risk.","created_at":t(3),"due_by":due(-30),"status_tracking":"pending","overdue":True,"idle_hours":3.0},
    {"ro":"20003","customer":"Ideal Cars","vehicle":"2011 Ford F-250","owner":"Preston","risk":"CRITICAL","priority":"P1","status":"Technical Advisement","task":"Technical direction needed. Diagnostic path is holding estimate.","created_at":t(4.5),"due_by":due(-60),"status_tracking":"pending","overdue":True,"idle_hours":4.5},

    # P1 INCOMING / ROLLING
    {"ro":"20004","customer":"Mike Planeta","vehicle":"2000 Ford Excursion","owner":"Drew","risk":"YELLOW","priority":"P1","status":"In Progress","task":"Near completion. Prepare for QC and closeout handoff.","created_at":t(1.0),"due_by":due(45),"status_tracking":"pending","overdue":False,"idle_hours":1.0},
    {"ro":"20005","customer":"Mitch Weber","vehicle":"2024 RAM 3500","owner":"Mitch","risk":"RED","priority":"P1","status":"Ready","task":"Ready for pickup. Contact customer, payment, and delivery closeout.","created_at":t(2.5),"due_by":due(-15),"status_tracking":"pending","overdue":True,"idle_hours":2.5},

    # P2 ACTION NOW
    {"ro":"20006","customer":"Ashley Jones","vehicle":"2017 Chevy Colorado","owner":"Drew","risk":"YELLOW","priority":"P2","status":"DVI updates","task":"Review DVI/photos. Advisor needs usable update for customer.","created_at":t(1.5),"due_by":due(20),"status_tracking":"pending","overdue":False,"idle_hours":1.5},
    {"ro":"20007","customer":"Pete Adams","vehicle":"2006 Dodge Ram 2500","owner":"Mitch","risk":"YELLOW","priority":"P2","status":"Advisor Estimate","task":"Review estimate and prepare customer presentation.","created_at":t(1.2),"due_by":due(30),"status_tracking":"pending","overdue":False,"idle_hours":1.2},
    {"ro":"20008","customer":"Fleet Unit 18","vehicle":"2016 Ford Explorer","owner":"Preston","risk":"YELLOW","priority":"P2","status":"Technical Overview","task":"Review technical overview and approve repair direction.","created_at":t(1.4),"due_by":due(45),"status_tracking":"pending","overdue":False,"idle_hours":1.4},

    # P2 INCOMING / ROLLING
    {"ro":"20009","customer":"Chris Evans","vehicle":"2022 Ford Explorer","owner":"Drew","risk":"NORMAL","priority":"P2","status":"Testing","task":"Tech verifying concern. Advisor update expected soon.","created_at":t(0.6),"due_by":due(90),"status_tracking":"pending","overdue":False,"idle_hours":0.6},
    {"ro":"20010","customer":"Terdell Dawes","vehicle":"2004 Ford F-250","owner":"Mitch","risk":"NORMAL","priority":"P2","status":"Advisor Estimate","task":"Estimate package almost ready. Prepare customer strategy.","created_at":t(0.8),"due_by":due(75),"status_tracking":"pending","overdue":False,"idle_hours":0.8},

    # P3 CONTROLLED WORK
    {"ro":"20011","customer":"Lisa Carter","vehicle":"2021 Toyota Camry","owner":"Drew","risk":"NORMAL","priority":"P3","status":"Servicing","task":"Work progressing normally. Monitor tech progress and ETA.","created_at":t(0.5),"due_by":due(180),"status_tracking":"pending","overdue":False,"idle_hours":0.5},
    {"ro":"20012","customer":"George Soto","vehicle":"2000 Ford F-250","owner":"Drew","risk":"NORMAL","priority":"P3","status":"Awaiting tech","task":"Parts ready. Dispatch when bay opens.","created_at":t(0.7),"due_by":due(150),"status_tracking":"pending","overdue":False,"idle_hours":0.7},
    {"ro":"20013","customer":"Bryan Wilson","vehicle":"2007 Ford E-450","owner":"Mitch","risk":"NORMAL","priority":"P3","status":"Waiting approval","task":"Customer has been updated. Monitor response window.","created_at":t(0.9),"due_by":due(240),"status_tracking":"pending","overdue":False,"idle_hours":0.9},
    {"ro":"20014","customer":"Marco Ramos","vehicle":"2015 RAM 1500","owner":"Preston","risk":"NORMAL","priority":"P3","status":"Technical Overview","task":"Non-urgent technical review. Customer expectation is safe.","created_at":t(0.4),"due_by":due(240),"status_tracking":"pending","overdue":False,"idle_hours":0.4},

    # P4 WAITING / EXTERNAL
    {"ro":"20015","customer":"David Wilson","vehicle":"2017 GMC Sierra","owner":"Mitch","risk":"NORMAL","priority":"P4","status":"Waiting parts","task":"Parts on order. ETA confirmed. Valid external wait.","created_at":t(5),"due_by":due(300),"status_tracking":"pending","overdue":False,"idle_hours":5.0},
    {"ro":"20016","customer":"Laisa Sanchez","vehicle":"1999 Ford F-350","owner":"Drew","risk":"NORMAL","priority":"P4","status":"Scheduled-Not Here","task":"Vehicle not here. Monitor only.","created_at":t(2),"due_by":due(480),"status_tracking":"pending","overdue":False,"idle_hours":2.0},
    {"ro":"20017","customer":"John Kingsley","vehicle":"2007 Toyota Camry","owner":"Mitch","risk":"NORMAL","priority":"P4","status":"DVI Only- Not Here","task":"DVI only scheduled vehicle not here yet. No active advisor task.","created_at":t(1),"due_by":due(480),"status_tracking":"pending","overdue":False,"idle_hours":1.0},
    {"ro":"20018","customer":"Apache Fleet","vehicle":"2018 RAM 2500","owner":"Preston","risk":"NORMAL","priority":"P4","status":"APACHE JOB","task":"Separate workflow. Monitor outside Country Club command board.","created_at":t(3),"due_by":due(480),"status_tracking":"pending","overdue":False,"idle_hours":3.0}
]

TASK_FILE.write_text(json.dumps(demo_tasks, indent=2), encoding="utf-8")
print("Demo command board loaded with P1-P4, all advisors, and column samples.")