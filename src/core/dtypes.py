import numpy as np

MAX_SYMBOLS          = 25
MAX_TICKS_PER_SYMBOL = 256
MAX_CANDLE_HISTORY   = 500
MAX_ACTIVE_TRADES    = 10
MAX_TRAILING         = 5
MAX_ORDERS           = 200

TICK_DTYPE = np.dtype([
    ('seq',        np.uint64),
    ('timestamp',  np.float64),
    ('ltp',        np.float64),
    ('volume',     np.int64),
    ('open_price', np.float64),
    ('high_price', np.float64),
    ('low_price',  np.float64),
    ('prev_close', np.float64),
])

CANDLE_DTYPE = np.dtype([
    ('seq',        np.uint64),
    ('open',       np.float64),
    ('high',       np.float64),
    ('low',        np.float64),
    ('close',      np.float64),
    ('volume',     np.int64),
    ('start_time', np.float64),
])


def make_ctrl_dtype(timeframes: list[int]) -> np.dtype:
    """
    Config ke timeframes se CTRL_DTYPE dynamically banao.
    Tick fields hamesha rahenge, candle fields TF list se generate honge.

    e.g. timeframes=[30, 60, 180] =>
        tick_seq, tick_widx,
        c30_seq, c30_widx, c30_bucket,
        c60_seq, c60_widx, c60_bucket,
        c180_seq, c180_widx, c180_bucket,
        _pad
    """
    fields = [
        ('tick_seq',  np.uint64),
        ('tick_widx', np.uint32),
    ]
    for tf in timeframes:
        fields += [
            (f'c{tf}_seq',    np.uint64),
            (f'c{tf}_widx',   np.uint32),
            (f'c{tf}_bucket', np.int64),
        ]
    fields.append(('_pad', np.uint8, (4,)))
    return np.dtype(fields)


ORDER_DTYPE = np.dtype([
    ('seq',            np.uint64),
    ('status',         np.int8),
    ('order_type',     np.int8),
    ('side',           np.int8),
    ('_pad',           np.uint8, (5,)),
    ('qty',            np.int32),
    ('stop_price',     np.float64),
    ('limit_price',    np.float64),
    ('traded_price',   np.float64),
    ('order_id',       'S64'),
    ('parent_id',      'S64'),
    ('symbol',         'S32'),
    ('order_datetime', 'S32'),
])

TRAILING_DTYPE = np.dtype([
    ('threshold', np.float64),
    ('new_stop',  np.float64),
    ('hit',       np.bool_),
    ('_pad',      np.uint8, (7,)),
])

TRADE_DTYPE = np.dtype([
    ('active',          np.bool_),
    ('_pad1',           np.uint8, (3,)),
    ('trade_no',        np.int32),
    ('qty',             np.int32),
    ('side',            np.int8),
    ('trailing_count',  np.int8),
    ('_pad2',           np.uint8, (6,)),
    ('entry_price',     np.float64),
    ('stop_price',      np.float64),
    ('target_price',    np.float64),
    ('order_id',        'S64'),
    ('stop_order_id',   'S64'),
    ('target_order_id', 'S64'),
    ('symbol',          'S32'),
    ('strategy_id',     'S32'),
    ('trailing',        TRAILING_DTYPE, (MAX_TRAILING,)),
])

ORDER_CTRL_DTYPE = np.dtype([
    ('widx', np.uint32),
    ('seq',  np.uint64),
])