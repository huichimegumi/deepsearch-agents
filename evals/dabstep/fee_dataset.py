"""Backward-compatible benchmark imports for the application fee dataset adapter."""

from app.research.fee_engine.dataset import FeeDataset, PaymentRecord

DABStepFeeDataset = FeeDataset

__all__ = ["DABStepFeeDataset", "FeeDataset", "PaymentRecord"]
