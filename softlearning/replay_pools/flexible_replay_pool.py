import numpy as np

from .replay_pool import ReplayPool


class FlexibleReplayPool(ReplayPool):
    def __init__(self, max_size, fields):
        super(FlexibleReplayPool, self).__init__()

        max_size = int(max_size)
        self._max_size = max_size

        self.fields = {}
        self.field_names = []
        self.add_fields(fields)

        self._pointer = 0
        self._size = 0

    @property
    def size(self):
        return self._size

    def add_fields(self, fields):
        self.fields.update(fields)
        self.field_names += list(fields.keys())

        for field_name, field_attrs in fields.items():
            field_shape = (self._max_size, *field_attrs['shape'])
            initializer = field_attrs.get('initializer', np.zeros)
            setattr(self, field_name, initializer(
                field_shape, dtype=field_attrs['dtype']))

    def _advance(self, count=1):
        self._pointer = (self._pointer + count) % self._max_size
        self._size = min(self._size + count, self._max_size)

    def add_sample(self, **kwargs):
        self.add_samples(1, **kwargs)

    def add_samples(self, num_samples=1, **kwargs):
        index = np.arange(
            self._pointer, self._pointer + num_samples) % self._max_size
        for field_name in self.field_names:
            values = (
                kwargs.pop(field_name, None)
                if field_name in kwargs
                else self.fields[field_name]['default_value'])
            getattr(self, field_name)[index] = values

        assert not kwargs, ("Got unexpected fields in the sample: ", kwargs)

        self._advance(num_samples)

    def random_indices(self, batch_size):
        if self._size == 0: return np.arange(0, 0)
        return np.random.randint(0, self._size, batch_size)

    def random_batch(self, batch_size, field_name_filter=None, **kwargs):
        random_indices = self.random_indices(batch_size)
        return self.batch_by_indices(
            random_indices, field_name_filter, **kwargs)

    def last_n_batch(self, last_n, field_name_filter=None, **kwargs):
        last_n_indices = np.arange(
            self._pointer - min(self.size, last_n), self._pointer
        ) % self._max_size
        return self.batch_by_indices(
            last_n_indices, field_name_filter, **kwargs)

    def batch_by_indices(self, indices, field_name_filter=None):
        if any(indices % self._max_size) > self.size:
            raise ValueError(
                "Tried to retrieve batch with indices greater than current"
                " size")

        field_names = self.field_names
        if field_name_filter is not None:
            field_names = [
                field_name for field_name in field_names
                if field_name_filter(field_name)
            ]

        return {
            field_name: getattr(self, field_name)[indices]
            for field_name in field_names
        }

    def __getstate__(self):
        state = self.__dict__.copy()
        if self.size < self._max_size:
            for field_name in self.field_names:
                state[field_name] = state[field_name][:self.size]

        return state

    def __setstate__(self, state):
        if state['_size'] < state['_max_size']:
            pad_size = state['_max_size'] - state['_size']
            for field_name in state['field_names']:
                field_shape = state['fields'][field_name]['shape']
                state[field_name] = np.concatenate((
                    state[field_name],
                    np.zeros((pad_size, *field_shape))
                ), axis=0)

        self.__dict__ = state
