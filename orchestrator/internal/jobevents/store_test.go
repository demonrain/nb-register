package jobevents

import (
	"testing"

	"google.golang.org/protobuf/encoding/protojson"

	"orchestrator/db"
	"orchestrator/pb"
)

func TestRowToProtoDecodesSnapshot(t *testing.T) {
	snapshot := &pb.JobSnapshot{
		EventId: 12,
		Job: &pb.Job{
			JobId:  "job-1",
			Status: "RUNNING",
		},
	}
	data, err := (protojson.MarshalOptions{UseProtoNames: true}).Marshal(snapshot)
	if err != nil {
		t.Fatalf("marshal snapshot: %v", err)
	}

	event, err := rowToProto(&db.JobEvent{
		EventID:      12,
		JobID:        "job-1",
		EventType:    "step_started",
		SnapshotJSON: string(data),
	})
	if err != nil {
		t.Fatalf("rowToProto returned error: %v", err)
	}
	if event.GetEventId() != 12 {
		t.Fatalf("event_id = %d; want 12", event.GetEventId())
	}
	if event.GetSnapshot().GetJob().GetStatus() != "RUNNING" {
		t.Fatalf("snapshot status = %q; want RUNNING", event.GetSnapshot().GetJob().GetStatus())
	}
}

func TestRowToProtoBackfillsSnapshotEventID(t *testing.T) {
	event, err := rowToProto(&db.JobEvent{
		EventID:   15,
		JobID:     "job-2",
		EventType: "job_updated",
	})
	if err != nil {
		t.Fatalf("rowToProto returned error: %v", err)
	}
	if event.GetSnapshot().GetEventId() != 15 {
		t.Fatalf("snapshot event_id = %d; want 15", event.GetSnapshot().GetEventId())
	}
}
