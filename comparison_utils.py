"""Shared data models and computation functions for quantized model comparison.

This module provides the core dataclasses and pure computation functions used by
both the comparison notebook and the test suite. It defines the data structures
for inference results and comparison results, along with functions for calculating
latency, throughput, cost, and aggregated metrics.
"""

import base64
import json
import os
import time

import boto3
import botocore.exceptions
import requests

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class InferenceResult:
    """Result of a single model inference invocation.

    Attributes:
        model_label: Human-readable label, e.g.
            "Qwen3-VL-8B — Quantized 4-bit GGUF (llama.cpp)".
        generated_text: The model's response text.
        latency_ms: End-to-end wall-clock latency in milliseconds.
        ttft_ms: Time-to-first-token in ms, or None if unavailable.
        token_count: Number of generated tokens.
        throughput_tps: Tokens per second.
        error: Error message if the invocation failed, otherwise None.
    """

    model_label: str
    generated_text: str
    latency_ms: float
    ttft_ms: float | None
    token_count: int
    throughput_tps: float
    error: str | None


@dataclass
class ComparisonResult:
    """Side-by-side comparison of quantized and full-precision inference.

    Attributes:
        prompt_text: The text instruction sent to both models.
        prompt_type: Either "image" or "text".
        image_source: Image path/URL for image prompts, None for text-only.
        quantized: Inference result from the quantized model.
        full_precision: Inference result from the full-precision model.
    """

    prompt_text: str
    prompt_type: str
    image_source: str | None
    quantized: InferenceResult
    full_precision: InferenceResult


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PRICING: dict[str, float] = {
    "ml.g5.xlarge": 1.41,     # USD/hour (us-east-2 on-demand) — fallback values
    "ml.g5.12xlarge": 7.09,   # USD/hour (us-east-2 on-demand) — fallback values
}


def get_live_pricing(instance_type: str, region: str = "us-east-2") -> float | None:
    """Fetch live SageMaker on-demand pricing from the AWS Pricing API.

    The Pricing API is only available in us-east-1 and ap-south-1.
    Returns the hourly price in USD, or None if the lookup fails.

    Args:
        instance_type: SageMaker instance type (e.g. "ml.g5.xlarge").
        region: AWS region code (e.g. "us-east-2").

    Returns:
        Hourly price in USD, or None if unavailable.
    """
    import json as _json

    # Map region codes to Pricing API location names
    region_names = {
        "us-east-1": "US East (N. Virginia)",
        "us-east-2": "US East (Ohio)",
        "us-west-1": "US West (N. California)",
        "us-west-2": "US West (Oregon)",
        "eu-west-1": "EU (Ireland)",
        "eu-central-1": "EU (Frankfurt)",
        "ap-southeast-1": "Asia Pacific (Singapore)",
        "ap-northeast-1": "Asia Pacific (Tokyo)",
    }

    location = region_names.get(region)
    if not location:
        return None

    try:
        # Pricing API is only available in us-east-1
        pricing_client = boto3.client("pricing", region_name="us-east-1")
        response = pricing_client.get_products(
            ServiceCode="AmazonSageMaker",
            Filters=[
                {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
                {"Type": "TERM_MATCH", "Field": "location", "Value": location},
                {"Type": "TERM_MATCH", "Field": "component", "Value": "Hosting"},
            ],
            MaxResults=1,
        )

        if not response["PriceList"]:
            return None

        price_data = _json.loads(response["PriceList"][0])
        terms = price_data["terms"]["OnDemand"]
        price_dimensions = list(list(terms.values())[0]["priceDimensions"].values())
        price_per_hour = float(price_dimensions[0]["pricePerUnit"]["USD"])
        return price_per_hour

    except Exception:
        return None


def get_pricing(region: str = "us-east-2") -> dict[str, float]:
    """Get SageMaker pricing, using live API with hardcoded fallbacks.

    Attempts to fetch live pricing from the AWS Pricing API. Falls back
    to hardcoded values if the API is unavailable.

    Args:
        region: AWS region code.

    Returns:
        Dict mapping instance type to hourly price in USD.
    """
    pricing = {}
    for instance_type, fallback_price in PRICING.items():
        live_price = get_live_pricing(instance_type, region)
        if live_price is not None and live_price > 0:
            pricing[instance_type] = live_price
        else:
            pricing[instance_type] = fallback_price
    return pricing


# ---------------------------------------------------------------------------
# Computation Functions
# ---------------------------------------------------------------------------


def calculate_latency(start: float, end: float) -> float:
    """Calculate latency in milliseconds from start and end timestamps.

    Args:
        start: Start timestamp in seconds (e.g. from ``time.time()``).
        end: End timestamp in seconds.

    Returns:
        Latency in milliseconds: ``(end - start) * 1000``.
    """
    return (end - start) * 1000


def calculate_throughput(token_count: int, latency_ms: float) -> float:
    """Calculate token generation throughput in tokens per second.

    Args:
        token_count: Number of tokens generated.
        latency_ms: End-to-end latency in milliseconds (must be > 0).

    Returns:
        Throughput in tokens per second: ``token_count / (latency_ms / 1000)``.
    """
    return token_count / (latency_ms / 1000)


def calculate_cost_per_request(latency_ms: float, hourly_price: float) -> float:
    """Estimate the cost of a single inference request.

    The cost is derived from the fraction of an hour consumed by the request
    multiplied by the hourly instance price.

    Args:
        latency_ms: Request latency in milliseconds (must be > 0).
        hourly_price: On-demand instance price in USD per hour.

    Returns:
        Estimated cost in USD: ``(latency_ms / 1000 / 3600) * hourly_price``.
    """
    return (latency_ms / 1000 / 3600) * hourly_price


def compute_average_metrics(
    results: list[ComparisonResult], metric: str
) -> tuple[float, float]:
    """Compute the average of a given metric for quantized and full-precision models.

    The *metric* parameter names an attribute on :class:`InferenceResult`
    (e.g. ``"latency_ms"``, ``"throughput_tps"``).

    Args:
        results: Non-empty list of comparison results.
        metric: Name of the ``InferenceResult`` attribute to average.

    Returns:
        A tuple ``(quantized_avg, full_precision_avg)``.

    Raises:
        ValueError: If *results* is empty.
        AttributeError: If *metric* is not a valid ``InferenceResult`` attribute.
    """
    if not results:
        raise ValueError("results must be non-empty")

    quantized_sum = 0.0
    full_precision_sum = 0.0

    for r in results:
        quantized_sum += getattr(r.quantized, metric)
        full_precision_sum += getattr(r.full_precision, metric)

    count = len(results)
    return quantized_sum / count, full_precision_sum / count


def compute_grouped_averages(results: list[ComparisonResult]) -> dict:
    """Partition results by prompt type and compute per-group average metrics.

    Groups results into ``"image"`` and ``"text"`` buckets based on
    :attr:`ComparisonResult.prompt_type`, then computes the average latency
    and throughput for both the quantized and full-precision models within
    each group.

    Args:
        results: List of comparison results (may be empty).

    Returns:
        A dict keyed by prompt type, where each value is a dict with::

            {
                "count": int,
                "quantized_avg_latency_ms": float,
                "quantized_avg_throughput_tps": float,
                "full_precision_avg_latency_ms": float,
                "full_precision_avg_throughput_tps": float,
            }

        Only prompt types present in *results* appear as keys.
    """
    groups: dict[str, list[ComparisonResult]] = {}
    for r in results:
        groups.setdefault(r.prompt_type, []).append(r)

    averages: dict[str, dict] = {}
    for prompt_type, group in groups.items():
        count = len(group)
        q_lat = sum(r.quantized.latency_ms for r in group) / count
        q_thr = sum(r.quantized.throughput_tps for r in group) / count
        fp_lat = sum(r.full_precision.latency_ms for r in group) / count
        fp_thr = sum(r.full_precision.throughput_tps for r in group) / count

        averages[prompt_type] = {
            "count": count,
            "quantized_avg_latency_ms": q_lat,
            "quantized_avg_throughput_tps": q_thr,
            "full_precision_avg_latency_ms": fp_lat,
            "full_precision_avg_throughput_tps": fp_thr,
        }

    return averages


# ---------------------------------------------------------------------------
# Image Encoding & Payload Builders
# ---------------------------------------------------------------------------


def encode_image(image_path_or_url: str) -> str:
    """Load an image from a local path or URL and return a base64-encoded string.

    If *image_path_or_url* starts with ``"http://"`` or ``"https://"``, the
    image is downloaded via HTTP.  Otherwise it is read from the local
    filesystem.

    Args:
        image_path_or_url: A local file path or an HTTP(S) URL pointing to
            an image.

    Returns:
        The base64-encoded image content as a string.

    Raises:
        IOError: If a local file cannot be read.
        requests.RequestException: If the HTTP download fails.
    """
    if image_path_or_url.startswith("http://") or image_path_or_url.startswith(
        "https://"
    ):
        response = requests.get(
            image_path_or_url,
            headers={"User-Agent": "QwenVL-Comparison-Notebook/1.0"},
            timeout=30,
        )
        response.raise_for_status()
        return base64.b64encode(response.content).decode("utf-8")
    else:
        with open(image_path_or_url, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")


def build_quantized_payload(
    prompt: str, image_b64: str | None, params: dict
) -> dict:
    """Build an OpenAI-compatible chat completion payload for the llama.cpp BYOC endpoint.

    For text-only prompts the message content is a plain string.  For image
    prompts the content is a list containing a text block and an
    ``image_url`` block with a base64 data URI.

    Args:
        prompt: The user instruction / question text.
        image_b64: Base64-encoded image data, or ``None`` for text-only.
        params: Additional generation parameters (e.g. ``max_tokens``,
            ``temperature``) included at the top level of the payload.

    Returns:
        A dict suitable for JSON-serialising and sending to the endpoint.
    """
    if image_b64 is not None:
        content = [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
            },
        ]
    else:
        content = prompt

    payload: dict = {
        "model": "quantized",
        "messages": [{"role": "user", "content": content}],
        **params,
    }
    return payload


def build_full_precision_payload(
    prompt: str, image_b64: str | None, params: dict
) -> dict:
    """Build an OpenAI-compatible payload for the LMI/vLLM full-precision endpoint.

    The SageMaker LMI container with vLLM also accepts the OpenAI-compatible
    chat completion format, so the structure mirrors
    :func:`build_quantized_payload`.

    Args:
        prompt: The user instruction / question text.
        image_b64: Base64-encoded image data, or ``None`` for text-only.
        params: Additional generation parameters (e.g. ``max_tokens``,
            ``temperature``) included at the top level of the payload.

    Returns:
        A dict suitable for JSON-serialising and sending to the endpoint.
    """
    if image_b64 is not None:
        content = [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
            },
        ]
    else:
        content = prompt

    payload: dict = {
        "model": "full_precision",
        "messages": [{"role": "user", "content": content}],
        **params,
    }
    return payload


# ---------------------------------------------------------------------------
# Endpoint Invocation & Comparison Orchestration
# ---------------------------------------------------------------------------


def invoke_endpoint(
    endpoint_name: str, payload: dict, runtime_client
) -> InferenceResult:
    """Send a payload to a SageMaker endpoint and return an InferenceResult.

    The *runtime_client* should be a ``boto3.client('sagemaker-runtime')``
    instance.  The function records wall-clock latency, parses the
    OpenAI-compatible JSON response, and extracts generated text and token
    count.

    Args:
        endpoint_name: Name of the SageMaker endpoint to invoke.
        payload: JSON-serialisable request payload.
        runtime_client: A ``boto3`` SageMaker Runtime client.

    Returns:
        An :class:`InferenceResult` populated with the response data and
        computed metrics, or with an error message if the invocation failed.
    """
    try:
        start = time.time()
        response = runtime_client.invoke_endpoint(
            EndpointName=endpoint_name,
            ContentType="application/json",
            Body=json.dumps(payload),
        )
        end = time.time()

        body = json.loads(response["Body"].read().decode("utf-8"))

        generated_text = body["choices"][0]["message"]["content"]

        usage = body.get("usage", {})
        token_count = usage.get("completion_tokens")
        if token_count is None:
            # Rough estimate: ~4 characters per token
            token_count = max(1, len(generated_text) // 4)

        latency_ms = calculate_latency(start, end)
        throughput_tps = calculate_throughput(token_count, latency_ms)

        return InferenceResult(
            model_label=endpoint_name,
            generated_text=generated_text,
            latency_ms=latency_ms,
            ttft_ms=None,
            token_count=token_count,
            throughput_tps=throughput_tps,
            error=None,
        )

    except botocore.exceptions.ClientError as exc:
        return InferenceResult(
            model_label=endpoint_name,
            generated_text="",
            latency_ms=0.0,
            ttft_ms=None,
            token_count=0,
            throughput_tps=0.0,
            error=f"ClientError: {exc}",
        )
    except json.JSONDecodeError as exc:
        return InferenceResult(
            model_label=endpoint_name,
            generated_text="",
            latency_ms=0.0,
            ttft_ms=None,
            token_count=0,
            throughput_tps=0.0,
            error=f"JSONDecodeError: {exc}",
        )
    except Exception as exc:
        return InferenceResult(
            model_label=endpoint_name,
            generated_text="",
            latency_ms=0.0,
            ttft_ms=None,
            token_count=0,
            throughput_tps=0.0,
            error=f"Error: {exc}",
        )


def run_comparison(
    prompt: str,
    image_source: str | None,
    params: dict,
    config: dict,
) -> ComparisonResult:
    """Orchestrate a single side-by-side comparison of both endpoints.

    Encodes the image (if provided), builds payloads for both endpoints,
    invokes them sequentially (quantized first, then full-precision), and
    returns a structured :class:`ComparisonResult`.

    Args:
        prompt: The text instruction / question to send to both models.
        image_source: A local file path or URL pointing to an image, or
            ``None`` for text-only prompts.
        params: Generation parameters (e.g. ``max_tokens``, ``temperature``)
            forwarded to both payload builders.
        config: A dict containing ``quantized_endpoint``,
            ``full_precision_endpoint``, and ``aws_region``.

    Returns:
        A :class:`ComparisonResult` with inference results from both models.
    """
    runtime_client = boto3.client(
        "sagemaker-runtime", region_name=config["aws_region"]
    )

    # Encode image if provided
    image_b64: str | None = None
    if image_source is not None:
        try:
            image_b64 = encode_image(image_source)
        except Exception as exc:
            # Image encoding failed — run both endpoints without the image
            # and record the error on both results.
            error_msg = f"Image encoding error: {exc}"
            failed_result = InferenceResult(
                model_label="",
                generated_text="",
                latency_ms=0.0,
                ttft_ms=None,
                token_count=0,
                throughput_tps=0.0,
                error=error_msg,
            )
            quantized_result = InferenceResult(
                model_label="Qwen3-VL-8B \u2014 Quantized 4-bit GGUF (llama.cpp)",
                generated_text="",
                latency_ms=0.0,
                ttft_ms=None,
                token_count=0,
                throughput_tps=0.0,
                error=error_msg,
            )
            full_precision_result = InferenceResult(
                model_label="Qwen3-VL-8B \u2014 Full Precision BF16 (vLLM)",
                generated_text="",
                latency_ms=0.0,
                ttft_ms=None,
                token_count=0,
                throughput_tps=0.0,
                error=error_msg,
            )
            prompt_type = "image" if image_source is not None else "text"
            return ComparisonResult(
                prompt_text=prompt,
                prompt_type=prompt_type,
                image_source=image_source,
                quantized=quantized_result,
                full_precision=full_precision_result,
            )

    # Build payloads
    quantized_payload = build_quantized_payload(prompt, image_b64, params)
    full_precision_payload = build_full_precision_payload(prompt, image_b64, params)

    # Invoke endpoints sequentially (quantized first to avoid contention)
    quantized_result = invoke_endpoint(
        config["quantized_endpoint"], quantized_payload, runtime_client
    )
    quantized_result.model_label = (
        "Qwen3-VL-8B \u2014 Quantized 4-bit GGUF (llama.cpp)"
    )

    full_precision_result = invoke_endpoint(
        config["full_precision_endpoint"], full_precision_payload, runtime_client
    )
    full_precision_result.model_label = (
        "Qwen3-VL-8B \u2014 Full Precision BF16 (vLLM)"
    )

    prompt_type = "image" if image_source is not None else "text"

    return ComparisonResult(
        prompt_text=prompt,
        prompt_type=prompt_type,
        image_source=image_source,
        quantized=quantized_result,
        full_precision=full_precision_result,
    )
