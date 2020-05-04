# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

import pandas as pd
import pickle
import pytest

from fairlearn.reductions import ExponentiatedGradient
from fairlearn.reductions import DemographicParity
from fairlearn.reductions import ErrorRate
from .simple_learners import LeastSquaresBinaryClassifierLearner
from .test_utilities import _get_data

from test.unit.input_convertors import conversions_for_1d, ensure_ndarray, \
    ensure_dataframe, _map_into_single_column
from test.unit.reductions.conftest import is_invalid_transformation

# ===============================================================

# Ways of transforming the data
candidate_X_transforms = [ensure_ndarray, ensure_dataframe]
candidate_Y_transforms = conversions_for_1d
candidate_A_transforms = conversions_for_1d

# ================================================================

_PRECISION = 1e-6


class TestExponentiatedGradientArguments:
    @pytest.mark.parametrize("transformA", candidate_A_transforms)
    @pytest.mark.parametrize("transformY", candidate_Y_transforms)
    @pytest.mark.parametrize("transformX", candidate_X_transforms)
    @pytest.mark.parametrize("A_two_dim", [False, True])
    @pytest.mark.uncollect_if(func=is_invalid_transformation)
    def test_argument_types(self, transformX, transformY, transformA, A_two_dim):
        # This is an expanded-out version of one of the smoke tests
        X, y, A = _get_data(A_two_dim)
        merged_A = _map_into_single_column(A)

        transformed_X = transformX(X)
        transformed_y = transformY(y)
        transformed_A = transformA(A)

        expgrad = ExponentiatedGradient(
            LeastSquaresBinaryClassifierLearner(),
            constraints=DemographicParity(),
            eps=0.1)
        expgrad.fit(transformed_X, transformed_y, sensitive_features=transformed_A)

        def Q(X): return expgrad._pmf_predict(X)[:, 1]
        n_predictors = len(expgrad._predictors)

        disparity_moment = DemographicParity()
        disparity_moment.load_data(X, y, sensitive_features=merged_A)
        error = ErrorRate()
        error.load_data(X, y, sensitive_features=merged_A)
        disparity = disparity_moment.gamma(Q).max()
        error = error.gamma(Q)[0]

        assert expgrad._best_gap == pytest.approx(0.0000, abs=_PRECISION)
        assert expgrad._last_t == 5
        assert expgrad._best_t == 5
        assert disparity == pytest.approx(0.1, abs=_PRECISION)
        assert error == pytest.approx(0.25, abs=_PRECISION)
        assert expgrad._n_oracle_calls == 32
        assert n_predictors == 3


# TODO: check logic of eps testing in conditional selection rate
class TestConditionalSelectionRateEps:
    @pytest.mark.parametrize("transformA", candidate_A_transforms)
    @pytest.mark.parametrize("transformY", candidate_Y_transforms)
    @pytest.mark.parametrize("transformX", candidate_X_transforms)
    @pytest.mark.parametrize("A_two_dim", [False, True])
    @pytest.mark.uncollect_if(func=is_invalid_transformation)
    def test_eps(self, transformX, transformY, transformA, A_two_dim):
        # This is an expanded-out version of one of the smoke tests
        X, y, A = _get_data(A_two_dim)
        merged_A = _map_into_single_column(A)

        expgrad = ExponentiatedGradient(
            LeastSquaresBinaryClassifierLearner(),
            constraints=DemographicParity(),
            eps=0.1)
        expgrad.fit(transformX(X), transformY(y), sensitive_features=transformA(A))

        def Q(X): return expgrad._pmf_predict(X)[:, 1]

        disparity_moment = DemographicParity()
        eps = 0.01
        disparity_moment.load_data(X, y, sensitive_features=merged_A, eps=eps)
        disparity_eps = disparity_moment.gamma(Q, with_RHS=True).max()
        disparity_no_eps = disparity_moment.gamma(Q, with_RHS=False).max()
        assert (np.isclose(np.abs(disparity_no_eps-disparity_eps), eps))

# TODO: check logic of eps testing in error rate
class TestErrorRateEps:
    @pytest.mark.parametrize("transformA", candidate_A_transforms)
    @pytest.mark.parametrize("transformY", candidate_Y_transforms)
    @pytest.mark.parametrize("transformX", candidate_X_transforms)
    @pytest.mark.parametrize("A_two_dim", [False, True])
    @pytest.mark.uncollect_if(func=is_invalid_transformation)
    def test_eps(self, transformX, transformY, transformA, A_two_dim):
        # This is an expanded-out version of one of the smoke tests
        X, y, A = _get_data(A_two_dim)
        merged_A = _map_into_single_column(A)

        expgrad = ExponentiatedGradient(
            LeastSquaresBinaryClassifierLearner(),
            constraints=DemographicParity(),
            eps=0.1)
        expgrad.fit(transformX(X), transformY(y), sensitive_features=transformA(A))

        def Q(X): return expgrad._pmf_predict(X)[:, 1]

        eps = 0.01
        error = ErrorRate()
        error.load_data(X, y, sensitive_features=merged_A, eps=eps)
        error_eps = error.gamma(Q, with_RHS=True)[0]
        error_noeps = error.gamma(Q, with_RHS=False)[0]

        assert (np.isclose(np.abs(error_noeps - error_eps), eps))

    @pytest.mark.parametrize("transformA", candidate_A_transforms)
    @pytest.mark.parametrize("transformY", candidate_Y_transforms)
    @pytest.mark.parametrize("transformX", candidate_X_transforms)
    def test_input_X_unchanged(self, transformA, transformY, transformX, mocker):
        # The purpose of this test is to ensure that X is passed to the underlying estimator
        # unchanged. For y and sample_weight ExponentiatedGradient makes certain transformations
        # which are required. They are expected as pandas.Series.
        X, y, A = _get_data()

        transformed_X = transformX(X)
        transformed_y = transformY(y)
        transformed_A = transformA(A)

        # Using a mocked estimator here since we don't actually want to fit one, but rather care
        # about having that object's fit method called exactly twice through the best_h calls.
        estimator = mocker.MagicMock()
        estimator.predict = mocker.MagicMock(return_value=y)
        # ExponentiatedGradient pickles and unpickles the estimator, which isn't possible for the
        # mock object, so we mock that process as well. It sets the result from pickle.loads as
        # the estimator, so we can simply overwrite the return value to be our mocked estimator
        # object.
        mocker.patch('pickle.dumps')
        pickle.loads = mocker.MagicMock(return_value=estimator)

        # restrict ExponentiatedGradient to a single iteration
        expgrad = ExponentiatedGradient(estimator, constraints=DemographicParity(), T=1)
        expgrad.fit(transformed_X, transformed_y, sensitive_features=transformed_A)

        # ensure that the input data wasn't changed by our mitigator before being passed to the
        # underlying estimator
        assert estimator.fit.call_count == 2
        for name, args, kwargs in estimator.method_calls:
            if name == 'fit':
                assert len(args) == 2  # X and y
                assert len(kwargs) == 1  # sample_weight
                assert isinstance(args[0], type(transformed_X))
                assert isinstance(args[1], pd.Series)
                assert isinstance(kwargs['sample_weight'], pd.Series)

