package main

import (
	"context"
	"orchestrator/pb"
	"strings"
)

func (s *orchestratorServer) GetJob(ctx context.Context, req *pb.GetJobRequest) (*pb.GetJobResponse, error) {
	jobID := strings.TrimSpace(req.GetJobId())
	if jobID == "" {
		return &pb.GetJobResponse{ErrorMessage: "job_id is required"}, nil
	}

	job, err := s.getJob(ctx, jobID)
	if err != nil {
		return &pb.GetJobResponse{ErrorMessage: err.Error()}, nil
	}

	steps, err := s.jobStore.Steps(ctx, jobID)
	if err != nil {
		return &pb.GetJobResponse{ErrorMessage: err.Error()}, nil
	}

	return &pb.GetJobResponse{Job: jobToProto(job, steps)}, nil
}
