package runtime

import (
	"context"
	"orchestrator/internal/contracts"
	"orchestrator/internal/jobevents"
	"orchestrator/internal/jobprojection"
	"orchestrator/pb"
	"strings"
)

func (s *orchestratorServer) GetJob(ctx context.Context, req *pb.GetJobRequest) (*pb.GetJobResponse, error) {
	jobID := strings.TrimSpace(req.GetJobId())
	if jobID == "" {
		return &pb.GetJobResponse{ErrorMessage: "job_id is required"}, nil
	}

	snapshot, err := s.jobStore.GetSnapshot(ctx, jobID)
	if err != nil {
		return &pb.GetJobResponse{ErrorMessage: err.Error()}, nil
	}

	s.withWorkflowProgress(ctx, snapshot)
	return &pb.GetJobResponse{Snapshot: snapshot}, nil
}

func (s *orchestratorServer) ListJobs(ctx context.Context, req *pb.ListJobsRequest) (*pb.ListJobsResponse, error) {
	snapshots, err := s.jobStore.ListSnapshots(ctx, jobprojection.ListFilter{
		Limit:     int(req.GetLimit()),
		Status:    req.GetStatus(),
		Action:    req.GetAction(),
		AccountID: req.GetAccountId(),
	})
	if err != nil {
		return &pb.ListJobsResponse{ErrorMessage: err.Error()}, nil
	}

	return &pb.ListJobsResponse{Snapshots: snapshots}, nil
}

func (s *orchestratorServer) WatchJob(req *pb.WatchJobRequest, stream pb.JobService_WatchJobServer) error {
	jobID := strings.TrimSpace(req.GetJobId())
	if jobID == "" {
		return stream.Send(&pb.WatchJobResponse{ErrorMessage: "job_id is required"})
	}
	if _, err := s.jobStore.GetSnapshot(stream.Context(), jobID); err != nil {
		return stream.Send(&pb.WatchJobResponse{ErrorMessage: err.Error()})
	}

	lastSent := req.GetAfterEventId()
	return s.watchJobEvents(stream.Context(), []string{jobID}, "", lastSent, func(event *pb.JobEvent) (bool, error) {
		if event == nil {
			return true, nil
		}
		if err := stream.Send(&pb.WatchJobResponse{Event: event}); err != nil {
			return false, err
		}
		return !snapshotIsTerminal(event.GetSnapshot()), nil
	})
}

func (s *orchestratorServer) WatchJobs(req *pb.WatchJobsRequest, stream pb.JobService_WatchJobsServer) error {
	lastSent := req.GetAfterEventId()
	return s.watchJobEvents(stream.Context(), req.GetJobIds(), req.GetStatus(), lastSent, func(event *pb.JobEvent) (bool, error) {
		if event == nil {
			return true, nil
		}
		if err := stream.Send(&pb.WatchJobsResponse{Event: event}); err != nil {
			return false, err
		}
		return true, nil
	})
}

func (s *orchestratorServer) watchJobEvents(ctx context.Context, jobIDs []string, status string, lastSent int64, send func(*pb.JobEvent) (bool, error)) error {
	if s.jobEvents == nil {
		_, err := send(nil)
		return err
	}
	ch, cancel := s.jobEvents.Subscribe(ctx)
	defer cancel()

	filter := jobevents.Filter{JobIDs: compactJobIDs(jobIDs)}
	status = strings.ToUpper(strings.TrimSpace(status))
	sendPending := func() (bool, error) {
		filter.AfterEventID = lastSent
		events, err := s.jobEvents.List(ctx, filter)
		if err != nil {
			return false, err
		}
		for _, event := range events {
			if event.GetEventId() <= lastSent {
				continue
			}
			if status != "" && !strings.EqualFold(event.GetSnapshot().GetJob().GetStatus(), status) {
				lastSent = event.GetEventId()
				continue
			}
			keepGoing, err := send(event)
			if err != nil || !keepGoing {
				return keepGoing, err
			}
			lastSent = event.GetEventId()
		}
		return true, nil
	}

	for {
		keepGoing, err := sendPending()
		if err != nil || !keepGoing {
			return err
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case _, ok := <-ch:
			if !ok {
				return nil
			}
		}
	}
}

func compactJobIDs(values []string) []string {
	out := make([]string, 0, len(values))
	seen := map[string]struct{}{}
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, ok := seen[value]; ok {
			continue
		}
		seen[value] = struct{}{}
		out = append(out, value)
	}
	return out
}

func (s *orchestratorServer) withWorkflowProgress(ctx context.Context, snapshot *pb.JobSnapshot) {
	if snapshot == nil || !snapshotIsRunning(snapshot) {
		return
	}
	job := snapshot.GetJob()
	workflowID, ok := contracts.WorkflowID(job.GetAction(), job.GetJobId())
	if ok && s.temporal != nil {
		query, err := s.temporal.QueryWorkflow(ctx, workflowID, "", workflowProgressQueryName)
		if err == nil {
			var progress WorkflowProgress
			if err := query.Get(&progress); err == nil {
				jobprojection.ApplyProgress(snapshot, &progress)
			}
		}
	}
}

func snapshotIsRunning(snapshot *pb.JobSnapshot) bool {
	return snapshot != nil && strings.EqualFold(strings.TrimSpace(snapshot.GetJob().GetStatus()), "RUNNING")
}

func snapshotIsTerminal(snapshot *pb.JobSnapshot) bool {
	if snapshot == nil || snapshot.GetJob() == nil {
		return false
	}
	status := strings.ToUpper(strings.TrimSpace(snapshot.GetJob().GetStatus()))
	return status == "SUCCEEDED" ||
		status == "FAILED_RETRYABLE" ||
		status == "FAILED_RECOVERABLE" ||
		status == "FAILED_FINAL"
}
