# Product Requirements Document (PRD)
## Real-Time Computer Vision-Based Detection of Unsafe Worker–Heavy Equipment Interactions on Construction Sites

**Version:** 1.0  
**Status:** MVP — Proposed  
**Product type:** Computer vision safety-monitoring 

## 1. Product Overview

The product is a computer vision-based safety-monitoring application that detects workers and heavy equipment in construction-site footage and identifies potentially unsafe proximity between them.

Using a pretrained object-detection model, the system analyses video frames, checks whether a worker enters a predefined danger zone around equipment, displays visual warnings, and records safety events for review.

The initial version will support uploaded videos, with live camera monitoring introduced as a later MVP enhancement. 

## 2. Problem Statement

Construction sites contain moving heavy equipment, including excavators and trucks, that can expose nearby workers to collision, crushing, and struck-by hazards.

Depending on continuous human observation alone can make it difficult to identify every unsafe interaction, particularly on busy sites or when equipment operators have restricted visibility.

The proposed system aims to provide an additional layer of monitoring by automatically identifying potential worker–equipment proximity hazards in video footage and making those events easier to review.

## 3. Product Goals

The MVP will:

- Detect workers in construction-site video footage.
- Identify the selected heavy equipment or its configured image region.
- Detect when a worker enters a predefined danger zone.
- Display visual warnings for potential unsafe interactions.
- Capture and store safety-event records with timestamps and evidence images.
- Provide a simple dashboard for reviewing detected events.

### Success criteria

- Successfully process a short test video from start to finish.
- Detect people in reasonably clear footage.
- Demonstrate danger-zone entry detection in predefined test scenarios.
- Save and display recorded alert events.
- Provide a usable demonstration without requiring specialised camera hardware.

Detection accuracy and processing speed will be measured during testing rather than assumed in advance.

## 4. Target Users

**Primary user: Site safety officer**

Needs to review potential hazards and identify situations requiring further investigation.

**Secondary user: Construction site supervisor**

Needs a quick overview of detected safety events and the ability to inspect relevant footage.

**Development and evaluation user**

Needs to test detection behaviour, configure danger zones, and assess system performance.

## 5. Scope

### In scope — MVP

1. Upload a video in a supported format.
2. Detect people using a pretrained computer vision model.
3. Configure a danger zone around one selected piece of equipment or a region in the video.
4. Identify when a detected worker enters that zone.
5. Annotate footage with bounding boxes and warning indicators.
6. Record the event timestamp, event type, and screenshot.
7. Display an event history dashboard.
8. Support basic configuration and testing of the detection threshold.

### Out of scope — Initial release

- Facial recognition or individual worker identification.
- Reliable measurement of real-world distance in metres.
- Automatic detection of every type of heavy equipment.
- PPE, helmet, and reflective-vest compliance detection.
- Multi-camera tracking.
- Mobile applications and cloud-scale deployment.
- Automatic stopping of equipment or activation of emergency controls.
- Claims of certified or guaranteed construction-site safety.

## 6. Core User Workflow

1. The user opens the application.
2. The user uploads a construction-site video.
3. The system processes the video and detects workers.
4. The user selects or configures the equipment danger zone.
5. The system identifies workers entering the zone.
6. Potential hazards are highlighted in the annotated footage.
7. The system saves the event timestamp and an evidence image.
8. The user opens the dashboard to review the events.

## 7. Functional Requirements

### FR-01: Video Upload

The system shall allow users to upload supported video files.

**Acceptance criteria:**
- The user can select and upload a video.
- The application validates the file type.
- The application displays a useful error for invalid or unreadable files.
- The user can initiate video processing.

### FR-02: Worker Detection

The system shall use a pretrained object-detection model to identify people in each processed frame.

**Acceptance criteria:**
- Detected people are marked with bounding boxes.
- The system displays a detection label and confidence score.
- Low-confidence detections can be filtered using a configurable threshold.

### FR-03: Equipment and Danger-Zone Configuration

The system shall allow the user to define a danger zone associated with the selected equipment.

For the initial implementation, the danger zone may be a manually configured polygon or region in the camera image.

**Acceptance criteria:**
- The user can configure the zone for the selected video view.
- The zone is displayed as an overlay.
- The system checks detected worker positions against the zone.
- The system does not require exact physical distance calculations.

### FR-04: Unsafe Interaction Detection

The system shall generate a potential-hazard event when a detected worker enters the configured danger zone.

**Acceptance criteria:**
- A worker entering the zone triggers a warning.
- The warning is visible in the annotated footage.
- The event is not repeatedly recorded on every frame while the same interaction continues.
- The system clears the warning when the interaction ends, subject to the configured detection rules.

### FR-05: Visual Alerts

The system shall display clear visual indicators for potential hazards.

**Acceptance criteria:**
- Potential hazards are visually distinguishable from ordinary detections.
- The interface displays a warning message.
- The warning identifies the event type and timestamp where available.

### FR-06: Event Logging

The system shall store a record for each detected potential-hazard event.

Each record should include:
- Event ID.
- Video or source identifier.
- Timestamp within the video.
- Event type.
- Equipment or configured zone identifier.
- Evidence screenshot path.
- Review status.

**Acceptance criteria:**
- Events are stored persistently.
- Duplicate events from the same continuous interaction are minimised.
- Users can view previously recorded events.

### FR-07: Safety Dashboard

The system shall provide a simple dashboard for monitoring and reviewing events.

**Acceptance criteria:**
- The dashboard displays the number of recorded events.
- Users can view an event list.
- Users can inspect the timestamp and evidence image.
- Users can distinguish new events from reviewed events.

### FR-08: Processing Feedback

The system shall indicate whether a video is waiting to be processed, processing, completed, or failed.

**Acceptance criteria:**
- Users receive visible processing feedback.
- Failed processing produces a useful error message.
- Users can retry processing when appropriate.

## 8. Non-Functional Requirements

**Performance**
- The application should process short test videos on a typical development computer.
- Processing speed and detection latency should be measured and documented.
- Live, real-time performance is not guaranteed until validated on the target hardware.

**Usability**
- The interface should be simple enough for a non-technical site supervisor to operate.
- Warnings and event timestamps should be easy to understand.

**Reliability**
- The system should handle missing detections and invalid video files without crashing.
- Continuous interactions should not create an excessive number of duplicate alerts.

**Privacy**
- Video files and captured evidence should be stored only in the configured local or authorised storage location.
- The MVP should avoid facial recognition and unnecessary personal-data collection.
- Access to footage should be restricted appropriately before any real-site deployment.

**Safety**
- Alerts shall be labelled as potential hazards requiring human review.
- The application shall not be represented as a substitute for trained safety personnel or established site safety procedures.

## 9. Proposed Technology Stack

| Component | Technology |
|---|---|
| Programming language | Python |
| Object detection | Ultralytics YOLO |
| Video processing | OpenCV |
| User interface | Streamlit |
| Event storage | SQLite |
| Evidence images | Local file storage |
| Version control | Git and GitHub |

The MVP should use pretrained weights initially. Custom model training should be considered only if testing shows that the required equipment cannot be detected reliably with the available model.

## 10. High-Level Architecture

**Video input → Frame extraction → Object detection → Danger-zone evaluation → Event generation → Evidence capture → Database storage → Dashboard**

The detection module should be separate from the dashboard logic so that a later version can accept a live camera stream without rebuilding the entire application.

## 11. Data Model

### SafetyEvent

| Field | Type |
|---|---|
| id | Integer or UUID |
| source_name | String |
| timestamp_seconds | Float |
| event_type | String |
| zone_id | String, nullable |
| evidence_path | String |
| review_status | String |
| created_at | Datetime |

A separate danger-zone configuration can store the zone name, coordinates, and associated video or camera identifier.

## 12. Development Roadmap

**Phase 1 — Object detection**
- Set up the Python environment.
- Load a sample construction video.
- Detect and annotate people.
- Test whether the selected equipment is detectable.

**Phase 2 — Danger-zone logic**
- Configure a zone around the equipment.
- Check worker positions against the zone.
- Implement warning states and duplicate-alert suppression.

**Phase 3 — Event logging**
- Capture evidence screenshots.
- Store timestamps and event records in SQLite.
- Verify event persistence.

**Phase 4 — Dashboard**
- Build the upload interface.
- Display annotated footage and processing status.
- Build the safety-event history page.

**Phase 5 — Testing and demonstration**
- Test clear and obstructed footage.
- Test zone entry and exit scenarios.
- Measure false alarms, missed events, and processing speed.
- Prepare a short demonstration.

**Phase 6 — Optional live monitoring**
- Connect a webcam or supported camera stream.
- Evaluate frame rate and detection latency.
- Test the system under different lighting and camera angles.

## 13. Testing and Evaluation

The system shall be tested against labelled or manually reviewed video scenarios.

Evaluation should measure:

- **Worker detection precision:** How often worker detections are correct.
- **Worker detection recall:** How many visible workers are successfully detected.
- **Event precision:** How many generated alerts correspond to actual zone-entry events.
- **Event recall:** How many labelled zone-entry events are detected.
- **Processing speed:** Frames processed per second.
- **Alert latency:** Time between a visible zone entry and the generated warning.

Test cases should include:
- A worker outside the danger zone.
- A worker entering the danger zone.
- A worker remaining inside the zone.
- A worker leaving the zone.
- Multiple workers near the equipment.
- Partial occlusion and missed detections.
- Equipment or workers moving out of the camera view.

## 14. Key Risks and Mitigations

**Risk: The pretrained model does not recognise excavators.**  
Mitigation: Test the model early, use a manually configured equipment region for the first demonstration, and consider fine-tuning on labelled images if necessary.

**Risk: False alarms caused by unstable detections.**  
Mitigation: Apply confidence thresholds, temporal persistence rules, and object tracking if required.

**Risk: Image-space distance does not represent physical distance.**  
Mitigation: Use a clearly defined image-space danger zone for the MVP and document its limitations.

**Risk: Poor performance on low-powered computers.**  
Mitigation: Reduce input resolution or process fewer frames, then measure the impact on detection quality.

**Risk: The system misses an actual hazard.**  
Mitigation: Test against reviewed footage, document limitations, and keep a human safety officer responsible for operational decisions.

## 15. Definition of Done

The MVP is complete when:

1. A user can upload and process a supported construction video.
2. The system detects workers in the footage.
3. A configured danger-zone entry triggers a visible potential-hazard warning.
4. The system records the event timestamp and an evidence screenshot.
5. The dashboard displays the recorded events.
6. The application handles invalid input and processing failures gracefully.
7. Testing results and known limitations are documented.
8. The application can be demonstrated end-to-end on a development computer.

## 16. Future Enhancements

After the MVP has been validated, possible enhancements include:
- Dedicated detection of excavators, forklifts, dump trucks, and cranes.
- Object tracking across frames.
- Equipment movement and direction estimation.
- Camera calibration for approximate physical-distance estimation.
- PPE compliance monitoring.
- Live CCTV integration.
- Notifications to authorised safety personnel.
- Multi-camera site monitoring and analytics.

## Final Product Vision

Build an accessible computer vision tool that helps construction teams identify and review potentially unsafe worker–equipment interactions using existing video footage.

The first release prioritises a working, testable demonstration of worker detection, danger-zone monitoring, and event logging. More advanced real-time safety capabilities will be added only after the core detection workflow has been evaluated.
