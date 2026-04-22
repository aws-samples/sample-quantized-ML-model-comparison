# Quantized Model Comparison — Terraform Configuration

> **⚠️ Important:** This Terraform configuration is provided as sample code for demonstration and educational purposes only. It is **not intended for production use**. IAM policies, network configurations, and security settings should be reviewed and hardened before deploying in a production environment.

## Overview

This Terraform configuration provisions two SageMaker real-time endpoints for comparing Unsloth's dynamically quantized Qwen3-VL-8B-Instruct (4-bit GGUF (GPT-Generated Unified Format) via llama.cpp) against the full-precision BF16 variant (via SageMaker LMI (Large Model Inference) with vLLM). It creates:

- An **Amazon ECR repository** and builds/pushes a custom Docker container (BYOC — Bring Your Own Container) running llama.cpp with CUDA support
- An **IAM execution role** with minimum permissions for SageMaker hosting and ECR access
- A **quantized model endpoint** (`ml.g5.xlarge`) serving the Q4_K_M GGUF model via llama.cpp
- A **full-precision endpoint** (`ml.g5.12xlarge`) serving the BF16 model via vLLM on SageMaker LMI

Both endpoints are used by the companion Jupyter notebook (`comparison_notebook.ipynb`) to run side-by-side inference comparisons focused on image understanding tasks.

## Prerequisites

- **AWS CLI** configured with credentials that have permissions to create SageMaker, ECR, IAM, CodeBuild, and S3 resources. If you haven't set up the AWS CLI, see the [AWS CLI Getting Started guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html).
- **Terraform** >= 1.0
- **No local Docker required** — the Docker image is built remotely via AWS CodeBuild
- **Sufficient SageMaker GPU quota** in `us-east-2`:
  - `ml.g5.xlarge` for endpoint usage (at least 1)
  - `ml.g5.12xlarge` for endpoint usage (at least 1) — **this often requires a quota increase request**

Check your quotas in the [AWS Service Quotas console](https://console.aws.amazon.com/servicequotas/) under "Amazon SageMaker" before deploying. To request a quota increase:

```bash
aws service-quotas request-service-quota-increase \
  --service-code sagemaker \
  --quota-code L-65C4BD00 \
  --desired-value 1 \
  --region us-east-2
```

## Quick Start

1. **Initialize Terraform**

   ```bash
   cd terraform
   terraform init
   ```

   This downloads the required AWS and null providers.

2. **Deploy the infrastructure**

   ```bash
   terraform apply
   ```

   Review the plan and type `yes` to confirm. This will:
   - Create an ECR repository (`qwen3-vl-llamacpp`)
   - Build the BYOC Docker image with llama.cpp and the quantized model weights, then push it to ECR
   - Create an IAM execution role for SageMaker
   - Deploy two SageMaker endpoints: one for the quantized model and one for the full-precision model

   The Docker build downloads ~6.4 GB of model weights and compiles llama.cpp with CUDA, so the first `apply` may take 15–30 minutes depending on your network and machine.

3. **Note the output endpoint names**

   After a successful apply, Terraform prints:

   ```
   quantized_endpoint_name = "qwen3-vl-8b-quantized"
   full_precision_endpoint_name = "qwen3-vl-8b-full-precision"
   ```

   Use these endpoint names in the notebook's configuration cell. You can retrieve them later with:

   ```bash
   terraform output
   ```

   Note that SageMaker endpoints can take **10–15 minutes** to reach `InService` status after Terraform reports completion.

## Configuration Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `aws_region` | AWS region for all resources | `us-east-2` |
| `quantized_instance_type` | SageMaker instance type for the quantized GGUF endpoint | `ml.g5.xlarge` |
| `full_precision_instance_type` | SageMaker instance type for the full-precision BF16 endpoint | `ml.g5.12xlarge` |

Override defaults with a `terraform.tfvars` file or command-line flags:

```bash
terraform apply -var="aws_region=us-west-2"
```

## Cleanup

Remove all provisioned resources to stop incurring costs:

```bash
terraform destroy
```

Review the plan and type `yes` to confirm. This removes both SageMaker endpoints, endpoint configurations, models, the ECR repository, and the IAM role.

> **Warning:** SageMaker endpoints incur charges as long as they are running. The `ml.g5.xlarge` costs approximately **$1.41/hr** and the `ml.g5.12xlarge` costs approximately **$7.09/hr** (us-east-2 on-demand pricing), for a combined total of **~$8.50/hr**. Always run `terraform destroy` or delete the endpoints from the notebook's cleanup cell when you are finished.

## Troubleshooting

### GPU Quota Errors

If endpoint creation fails with a quota error like `ResourceLimitExceeded`, you need to request a quota increase:

1. Open the [AWS Service Quotas console](https://console.aws.amazon.com/servicequotas/)
2. Navigate to **Amazon SageMaker**
3. Search for the instance type (e.g., `ml.g5.xlarge for endpoint usage`)
4. Click **Request quota increase** and request at least 1 instance for each type needed

Quota increases are typically approved within a few hours but may take up to a few days.

### ECR Push Failures

If the Docker image fails to push to ECR:

- **Authentication**: Ensure your AWS CLI credentials are valid and have ECR permissions. Re-authenticate with:
  ```bash
  aws ecr get-login-password --region us-east-2 | docker login --username AWS --password-stdin <account_id>.dkr.ecr.us-east-2.amazonaws.com
  ```
- **Network connectivity**: Verify you can reach the ECR endpoint. Check proxy settings or VPN configurations if applicable.
- **Docker daemon**: Confirm Docker is running with `docker info`.

### Endpoint Creation Timeout

SageMaker endpoints can take **10–15 minutes** to become `InService`. If Terraform appears to hang during endpoint creation, this is normal. You can monitor progress in the [SageMaker console](https://console.aws.amazon.com/sagemaker/) under **Inference > Endpoints**.

If an endpoint fails to reach `InService`:

- Check the endpoint's CloudWatch logs for container startup errors
- Verify the Docker image was pushed successfully to ECR
- Ensure the instance type has sufficient GPU memory for the model (both models fit within the 24 GB A10G GPU)
