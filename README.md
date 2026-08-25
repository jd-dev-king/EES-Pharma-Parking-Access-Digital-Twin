EES Pharma Parking Access Digital Twin

Version 3.0.1

A secure employee, contractor, and visitor parking-access digital twin
for a pharmaceutical manufacturing facility, built as part of the EES
Industrial Universe.

Version 3.0.1 expands the database-integrated parking twin with a
shift-driven accelerated Auto Run, a 30-space secured overflow
lot, workforce-backed employee authorization, automated contractor and
visitor scenarios, Security review events, and full secured/overflow
occupancy visualization.

The application combines:

Browser-based Three.js parking simulation

Virtual PLC gate logic

FastAPI services

PostgreSQL-backed operational state

Workforce-linked employee vehicle authorization

Security approval and exception workflows

Shift-driven accelerated simulation

70-space secured parking

30-space secured overflow parking

Live occupancy and parking rosters

Industrial HMI visualization

EES Pharma Process Twin integration

The authoritative data platform is:

ees_data_platform

Project Overview

The EES Pharma Parking Access Digital Twin models the facility-access
layer surrounding the EES pharmaceutical manufacturing environment.

The parking system now manages 100 operational parking spaces:

Parking Area                              Capacity Purpose

Secured Main Lot                                70 Primary employee,
contractor, and
approved visitor
parking

Secured Overflow Lot                            30 Capacity overflow
during shift-driven
traffic

The system supports:

Employee vehicle recognition

Workforce-backed employee authorization

Employee access exceptions

Security overrides

Contractor arrivals

Visitor approval

Temporary visitor identifiers

Security review events

Entry and exit gate control

Main-lot parking assignment

Overflow-lot parking assignment

Live secured-lot occupancy

Live overflow occupancy

Shift-driven Auto Run cycles

Automated arrival and departure processing

Parking-space release

Security event logging

Virtual PLC logic

PostgreSQL persistence

Three.js 3D visualization

Pharma Process Twin parking/security integration

EES Universal Data Moon registration

Manual controls remain available for deterministic testing while Auto
Run provides a fast portfolio demonstration of a complete operating
cycle.

EES Universe Architecture

The Parking Access Digital Twin is one operational component of the
larger EES Industrial Universe.

                         EES INDUSTRIAL UNIVERSE
                                  │
                                  ▼
                         ees_data_platform
                          PostgreSQL Database
                                  │
              ┌───────────────────┼───────────────────────┐
              │                   │                       │
              ▼                   ▼                       ▼
         power_grid.*          pharma.*              workforce.*
                                                          │
                                                          ▼
                                                  parking_access.*
                                                          │
                                      ┌───────────────────┴───────────────────┐
                                      ▼                                       ▼
                         Pharma Parking Access Twin                Pharma Process Twin
                                      │                                       │
                                      ▼                                       ▼
                         PLC / HMI / Security                 Security / 3D Overview
                                      │                                       │
                                      └───────────────────┬───────────────────┘
                                                          ▼
                                                   analytics / EES

The shared PostgreSQL platform remains the authoritative data source for
EES operational data. Parking Access uses the parking_access domain
while employee identity and employment state are linked to the shared
workforce model.

Technology Stack

Frontend

HTML5

CSS3

JavaScript

Three.js

Browser-based virtual PLC

Industrial HMI

Accelerated simulation controls

Secured and overflow parking visualization

Backend

Python

FastAPI

Uvicorn

Psycopg

Psycopg connection pooling

PostgreSQL

Database

PostgreSQL

Canonical database: ees_data_platform

Parking schema: parking_access

Workforce integration: workforce

EES Integration

ees_registry

workforce

parking_access

EES Pharma Process Twin

EES Universal Data Moon

Future Smart Assistant AI integration

Future Manufacturing Intelligence analytics

Future Power Grid / facility cross-domain events

Major Features

1. 70-Space Secured Main Lot

The Three.js environment presents a controlled pharmaceutical employee
parking facility containing 70 secured parking spaces.

The HMI tracks:

Secured occupancy

Secured spaces available

Employee count

Contractor count

Visitor count

Lot full state

Lot empty state

When the secured lot reaches capacity, eligible incoming Auto Run
traffic can be routed to the overflow lot rather than being discarded.

2. 30-Space Secured Overflow Lot

Version 3.0.1 adds a dedicated 30-space overflow parking area.

The overflow lot is operational rather than decorative. Overflow
assignments are represented as real parking state and are visible in the
Three.js scene.

The system tracks:

Secured Lot       0 / 70
Overflow Lot      0 / 30
Total Parked      0 / 100

Overflow processing supports:

Overflow space allocation

Persistent overflow assignments

Vehicle visualization

Overflow occupancy counters

Overflow departure processing

Overflow space release

Auto Run routing

Security/overview integration

The main and overflow lots are visually separated in the 3D scene and
use distinct parking-space presentations.

3. Workforce-Backed Employee Vehicle Authorization

Employee parking authorization is linked to the EES workforce model
rather than relying only on isolated parking demo identities.

Registered employee vehicles are associated with workforce employees,
allowing Parking Access to evaluate operational workforce attributes
such as:

Employee number

Display name

Employment status

Employment type

Commute mode

Parking authorization

Active vehicle registration

A recognized employee vehicle can receive automatic access when:

Employment Status = ACTIVE
Commute Mode      = VEHICLE
Parking Authorized = TRUE

and parking capacity is available.

This keeps employee identity authoritative across EES systems while
allowing the parking domain to retain vehicle and parking-specific
state.

4. Employee Access Exception Workflow

Known employees who do not meet normal parking authorization
requirements are not converted into visitors.

Examples include:

Employee on leave

Inactive employee

Parking authorization suspended

Employee not assigned to vehicle parking

These requests become an employee access exception and are routed to
Security.

Security can:

Approve Employee Override + Open Gate

or:

Deny Employee Access

Approved employee overrides remain classified as employee parking
sessions and do not consume visitor credentials.

5. Visitor Access Workflow

Unknown vehicle identifiers do not receive automatic entry.

Unknown Vehicle
      │
      ▼
Gate Remains Closed
      │
      ▼
Security Review
      │
      ├── Deny Access
      │
      └── Approve Visitor
               │
               ▼
        Assign VIS-####
               │
               ▼
        Open Entry Gate
               │
               ▼
        Create Parking Session

Visitor IDs are allocated from the PostgreSQL-backed visitor pool.

Visitor sessions remain independently classified from employee and
contractor traffic.

6. Contractor Traffic

The accelerated operating cycle includes planned contractor arrivals.

Contractors are tracked independently so the HMI and integrated Pharma
Process views can distinguish:

Employees
Contractors
Visitors

Contractor traffic participates in normal parking-capacity decisions and
can be routed to overflow when required by the simulated operating
cycle.

Shift-Driven Accelerated Auto Run

Version 3.0.1 introduces the production demonstration mode for
accelerated shift-driven parking simulation.

The purpose is to let a portfolio visitor observe a complete facility
parking cycle quickly instead of waiting through real-world shift
durations.

The Auto Run executes a compressed operational schedule that can
include:

Shift preparation
      │
      ▼
Employee arrivals
      │
      ▼
Contractor arrivals
      │
      ▼
Visitor / Security scenarios
      │
      ▼
Secured lot reaches capacity
      │
      ▼
Overflow routing
      │
      ▼
Shift occupancy
      │
      ▼
Vehicle departures
      │
      ▼
Overflow departures
      │
      ▼
Lot returns to empty
      │
      ▼
Cycle complete

Auto Run HMI

The Accelerated Simulation panel displays live state including:

Auto Run active/inactive state

Simulation cycle

Simulated day

Simulation clock

Current phase

Current event

Next event

Secured-lot occupancy

Employee count

Contractor count

Visitor count

Overflow occupancy

Completed entries

Completed exits

Typical phases include operational events such as:

EMPLOYEE_ARRIVAL
CONTRACTOR_ARRIVAL
VISITOR_ARRIVAL
OVERFLOW
DEPARTURE
COMPLETE

The exact phase sequence is driven by the backend simulation schedule.

Accelerated Demonstration Design

Auto Run intentionally operates faster than real time.

It is designed to demonstrate:

Shift-change congestion

Employee authorization

Contractor arrivals

Visitor Security review

Main-lot saturation

Overflow routing

Entry gate operation

Exit gate operation

Occupancy changes

Departure processing

Full-cycle recovery to an empty lot

This is a simulation feature for portfolio and systems-integration
demonstration; it is not a real facility scheduling engine.

Overflow Routing Logic

When the secured 70-space lot has available capacity, vehicles are
assigned there first.

When the secured lot reaches capacity:

Incoming Authorized Vehicle
          │
          ▼
Secured Lot Full?
     │          │
    NO         YES
     │          │
     ▼          ▼
Main Lot    Overflow Available?
                 │          │
                YES         NO
                 │          │
                 ▼          ▼
           Overflow Lot   Capacity Event

Overflow assignments remain visible and operational until the associated
vehicle departs.

The combined capacity is:

70 secured + 30 overflow = 100 total spaces

Entry and Exit Gate Visualization

Both manual and Auto Run transactions drive the parking gate
visualization.

During an authorized entry:

Vehicle is detected.

Authorization is evaluated.

Parking destination is determined.

Entry gate opens.

Vehicle is assigned to the secured or overflow lot.

Gate returns to its secure state.

During exit:

Vehicle is detected at exit.

Active parking assignment is located.

Exit is authorized.

Exit gate opens.

Parking session is closed.

Main or overflow space is released.

Gate returns to its secure state.

The gate animation is synchronized with the accelerated demonstration so
visitors can see access-control activity during Auto Run.

Parking Entry Workflow

For a normally authorized employee:

Vehicle Detected
      │
      ▼
Workforce + Vehicle Lookup
      │
      ▼
Employee Vehicle Found
      │
      ▼
Employee Active?
      │
      ▼
Vehicle Commute?
      │
      ▼
Parking Authorized?
      │
      ▼
Parking Capacity?
      │
      ├── Main Lot Available ──► Assign Secured Space
      │
      └── Main Lot Full ───────► Evaluate Overflow
                                      │
                                      ▼
                                Assign Overflow Space
      │
      ▼
Entry Gate Opens
      │
      ▼
Parking Session Created
      │
      ▼
Occupancy Updated

Parking Exit Workflow

Vehicle Detected at Exit
        │
        ▼
Locate Active Parking Assignment
        │
        ▼
Identify Secured / Overflow Destination
        │
        ▼
Authorize Exit
        │
        ▼
Open Exit Barrier
        │
        ▼
Close Parking Session
        │
        ▼
Release Assigned Space
        │
        ▼
Update Occupancy

Visitor sessions additionally update the visitor-pass lifecycle.

Live Occupancy

The HMI provides live database-backed parking state for the combined
facility.

Example:

SECURED LOT
70 / 70

OVERFLOW
11 / 30

TOTAL PARKED
81 / 100

Separate occupant counters are maintained for:

Employees

Contractors

Visitors

The system can expose active parking assignments with information such
as:

Employee or temporary identity

Vehicle identifier

Occupant classification

Parking area

Assigned space

Entry timestamp

Session state

Restart Demo / Reset Lot

The Live Occupancy panel includes:

Restart Demo / Reset Lot

This returns the simulator to a clean demonstration state while
preserving historical audit information.

The reset process returns the operational view to:

Secured       0 / 70
Overflow      0 / 30
Total         0 / 100
Employees     0
Contractors   0
Visitors      0

It also clears or closes applicable active simulation state so a new
demonstration can begin cleanly.

Virtual PLC

The application includes a browser-based virtual PLC scan.

Representative PLC tags include:

Vehicle_Detected
Employee_Vehicle
Visitor_Vehicle
Vehicle_Authorized
Security_Approval
Entry_Gate_Open
Exit_Gate_Open
Car_Count
Spots_Remaining

The PLC executes on an approximately:

100 ms

browser simulation cycle.

The HMI displays the scan counter and current logical states.

Secure Entry Logic

Conceptually, entry authorization follows:

Vehicle_Detected
       │
       ▼
Identity / Vehicle Lookup
       │
       ▼
Authorization
       │
       ├──────────────┐
       │              │
       ▼              ▼
Normal Access    Security Override
       │              │
       └───────OR─────┘
               │
               ▼
        Parking Capacity
               │
               ▼
        Main or Overflow
               │
               ▼
     AND NOT Emergency_Stop
               │
               ▼
        Entry_Gate_Open

This models a simplified IEC 61131-3-style industrial control workflow.

Holographic HMI

The industrial HMI displays:

Entry gate status

Exit gate status

Main-lot full state

Main-lot empty state

Database state

Visitor ID availability

PLC scan count

Secured occupancy

Overflow occupancy

Total parking capacity

Employee occupancy

Contractor occupancy

Visitor occupancy

Access-control decisions

Security requests

Auto Run state

Simulation phase

Simulation clock

Current event

Next event

Emergency Stop

The HMI includes an Emergency Stop control.

When active, access-control gate commands are prevented from energizing
regardless of authorization state.

This models the safety-priority behavior expected from industrial
control systems.

PostgreSQL Data Model

The parking domain uses:

parking_access

inside:

ees_data_platform

Core parking objects include data for:

Employee vehicle registration

Parking spaces

Parking sessions

Visitor passes

Security requests

Security actions

Access events

Overflow parking state

Accelerated simulation state

Employee identity and employment state are linked to the shared
workforce domain.

This architecture keeps business and operational data in the canonical
EES PostgreSQL platform instead of making browser state authoritative.

Parking Sessions

A successful parking transaction creates an operational parking
assignment/session.

The session can track:

Vehicle identifier

Occupant type

Employee vehicle reference when applicable

Visitor pass when applicable

Parking destination

Parking space

Entry timestamp

Exit timestamp

Session status

Security request when applicable

An active assignment represents a vehicle currently parked in either the
secured or overflow facility.

Security Requests

Security exceptions are persisted so authorization decisions remain
auditable.

Requests can represent scenarios such as:

UNKNOWN VISITOR

or:

EMPLOYEE ACCESS EXCEPTION

Auto Run can also generate visitor/Security activity so the Security
workflow is visible during an accelerated demonstration.

Security actions record approval or denial decisions.

Pharma Process Twin Integration

Parking Access publishes facility parking state for the EES Pharma
Process Twin.

The Pharma Process Security Command Center and 3D facility overview can
display:

Secured-lot occupancy

Overflow-lot occupancy

Total parked

Total available

Employees on site

Contractors on site

Visitors on site

Pending Security reviews

Auto Run state

Auto Run phase

Simulation clock

Active secured assignments

Active overflow assignments

This allows the parking subsystem to remain independently deployable
while presenting its operational state inside the larger Pharma Process
environment.

EES Universal Data Moon Registration

The Parking Access Digital Twin registers itself with the EES registry
using the facility-access domain.

Representative identity:

system_name:
EES Pharma Parking Access Digital Twin

system_key:
ees-pharma-parking-access

domain:
facility-access

system_type:
industrial-access-digital-twin

primary_database:
ees_data_platform

This allows other EES systems to discover the Parking Twin
programmatically.

Local Installation

Requirements

Recommended:

Python 3.10+
PostgreSQL
Modern web browser

1. Enter the Project

cd '/Users/your-user/Documents/GitHub/EES Universe/EES-Pharma-Parking-Access-Digital-Twin'

2. Create and Activate the Python Environment

From the backend directory or according to your local environment
layout:

python3 -m venv .venv
source .venv/bin/activate

3. Install Backend Dependencies

cd backend
pip install -r requirements.txt

4. Configure PostgreSQL

Create or update:

backend/.env

Example:

DATABASE_URL=postgresql://your_postgres_user@localhost:5432/ees_data_platform
API_HOST=0.0.0.0
API_PORT=8001
CORS_ORIGINS=http://localhost:5501,http://127.0.0.1:5501

Do not commit .env files containing credentials.

Operational/database data for production should be managed through the
authoritative PostgreSQL platform rather than treating local seed files
as the production source of truth.

Running the Application

Two local processes are required.

Terminal 1 --- FastAPI Backend

cd backend
source .venv/bin/activate
python -m uvicorn main:app --host 127.0.0.1 --port 8001

Backend:

http://127.0.0.1:8001

Terminal 2 --- Frontend

From the project root:

python3 -m http.server 5501

Application:

http://127.0.0.1:5501

API Verification

Health:

curl -s http://127.0.0.1:8001/api/health | python3 -m json.tool

Demo/workforce identifiers:

curl -s http://127.0.0.1:8001/api/demo/identifiers | python3 -m json.tool

Parking status:

curl -s http://127.0.0.1:8001/api/parking/status | python3 -m json.tool

Auto Run status:

curl -s http://127.0.0.1:8001/api/auto-run/status | python3 -m json.tool

Use the application's currently implemented API routes as the
authoritative endpoint list if routes change in later releases.

Demonstration Workflows

Manual Authorized Employee

Select or enter a known authorized employee vehicle.

Detect at Entry.

Workforce and parking authorization succeed.

Entry barrier opens.

A parking destination is assigned.

Occupancy increases.

Detect at Exit.

Exit barrier opens.

Session closes.

Occupancy decreases.

Manual Employee Exception

Use a known employee whose employment or parking state requires Security
review.

Detect at Entry.

Employee identity is recognized.

Normal authorization fails.

Security Review appears.

Security approves an employee override or denies access.

Approved access remains classified as an employee session.

Manual Visitor

Enter an unknown vehicle identifier.

Vehicle remains at the closed entry barrier.

Security request is generated.

The next available visitor identifier is presented.

Security approves or denies access.

Approved visitor receives the temporary identifier.

Gate opens.

Visitor parking session begins.

Accelerated Shift Auto Run

Reset the lot if required.

Select Start Auto Run.

Observe simulated shift time advance.

Employee arrivals begin.

Contractor traffic is processed.

Visitor/Security scenarios are generated.

Main-lot occupancy increases.

When the secured lot reaches 70/70, additional eligible traffic is
routed to overflow.

Overflow vehicles appear in the 30-space overflow lot.

Departure processing releases secured and overflow spaces.

The simulation returns the facility to an empty state.

Auto Run reports the cycle as complete and ready for replay.

Manual and Auto Modes

Version 3.0.1 supports both operational demonstration styles.

Manual Mode

Manual mode is intended for deterministic inspection of:

Individual vehicle authorization

Employee exceptions

Visitor Security review

Gate behavior

Parking assignment

Exit behavior

Database persistence

Auto Run

Auto Run is intended for a rapid end-to-end portfolio demonstration.

It uses a shift-driven schedule to show how parking access behaves as a
connected operational system under changing demand.

Manual controls remain available after the automated cycle completes.

Security Design

The project demonstrates the distinction between:

Identity
Authorization
Security Override
Parking Destination

A known employee remains an employee even when normal parking
authorization fails.

A visitor remains a separate temporary identity class.

Overflow is a parking destination, not an occupant classification. A
vehicle routed to overflow retains its employee, contractor, or visitor
identity.

This preserves cleaner operational and audit semantics.

Pharmaceutical Manufacturing Context

Although this project is a portfolio-scale digital twin, the design
reflects concepts relevant to controlled pharmaceutical manufacturing
environments:

Controlled site access

Employee identity management

Visitor management

Contractor access

Security review

Auditability

Restricted-access workflows

Event traceability

Shift-change operations

Capacity management

Separation of operational roles

Industrial HMI visualization

Database-backed system state

Cross-system facility visibility

The simulator does not represent a validated production access-control
system and should not be used as one.

Repository Structure

EES-Pharma-Parking-Access-Digital-Twin/
│
├── index.html
├── style.css
├── app.js
├── config.js
├── README.md
├── LICENSE
│
└── backend/
    ├── main.py
    ├── db.py
    ├── requirements.txt
    ├── .env.example
    └── ...

Version 3.0.1 Highlights

Version 3.0.1 expands the database-integrated parking twin into a
complete accelerated facility parking demonstration.

Major improvements include:

Shift-driven accelerated Auto Run

Compressed full operating-cycle demonstration

70-space secured main lot

30-space secured overflow lot

100-space combined operational capacity

Persistent overflow assignments

Visible overflow vehicles in the Three.js scene

Overflow arrival and departure processing

Main-to-overflow routing when the secured lot is full

Employee arrival simulation

Contractor arrival simulation

Visitor/Security scenarios

Live Auto Run phase and simulation clock

Current-event and next-event HMI reporting

Automated entry and exit gate visualization

Workforce-backed employee authorization

Employee access exception preservation

Live employee, contractor, and visitor counts

Secured, overflow, and total parking metrics

Pharma Process Security Command Center integration

Pharma Process 3D overview integration

Database-backed operational state

Virtual PLC and industrial HMI integration

Audit-oriented Security workflows

Suggested Future Enhancements

Potential future EES integration opportunities include:

Smart Assistant AI parking queries

Manufacturing Intelligence parking analytics

Parking demand forecasting

Shift schedule optimization

EV charging spaces

ADA / reserved space modeling

Delivery vehicle security

Parking-space reservation

Badge reader simulation

License-plate recognition simulation

PLC ladder/FBD visualization

Power Grid Sun parking electrical loads

Camera/security telemetry

Access anomaly detection

Multi-lot Pharma campus expansion

Smart Assistant AI Integration

A future EES Smart Assistant AI can query parking information through
the EES data platform.

Examples:

How many employees are currently parked?

How many vehicles are in overflow?

Which contractors are currently on site?

How many spaces remain across both lots?

Show today's denied parking requests.

What phase is the parking Auto Run currently in?

This allows Parking Access to become another operational domain
available to the EES intelligence layer.

Author

EES Portfolio Universe Exclusive by Jeremiah Lupton (JDL)

License

This project is licensed under the MIT License.

See:

LICENSE

for details.

EES Industrial Universe

The EES Industrial Universe is a connected portfolio of industrial
digital twins, data engineering systems, manufacturing intelligence
tools, controls simulations, and AI-enabled operational systems.

The long-term objective is to demonstrate how independent operational
systems can share a common data platform while preserving their
individual domain responsibilities.

Power
Controls
Manufacturing
Supply
Facility Access
Workforce
Analytics
Artificial Intelligence
        │
        ▼
EES Industrial Universe

EES Pharma Parking Access Digital Twin · v3.0.1

Secure Access · Shift Auto Run · Overflow Parking · Virtual PLC ·
FastAPI · PostgreSQL · Three.js · EES Universe
