import numpy as np

MAX_SYMBOLS          = 25
MAX_TICKS_PER_SYMBOL = 256
MAX_CANDLE_HISTORY   = 500
MAX_ACTIVE_TRADES    = 10
MAX_TRAILING         = 5
MAX_ORDERS           = 200
MAX_TF               = 8        # max supported timeframes

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

# Fixed layout — MAX_TF slots, integer indexed.
# tf_map (built at startup) provides: tf_value → slot_index
# Hot path: ctrl['tf_widx'][tf_idx]  — integer index, direct byte offset
# No string formatting, no runtime dtype field resolution.
CTRL_DTYPE = np.dtype([
    ('tick_seq',  np.uint64),
    ('tick_widx', np.uint32),
    ('_pad0',     np.uint8, (4,)),          # align tf_seq to 8-byte boundary
    ('tf_seq',    np.uint64, (MAX_TF,)),    # candle sequence counter per TF
    ('tf_widx',   np.uint32, (MAX_TF,)),    # candle write index per TF
    ('_pad1',     np.uint8, (4,)),          # align tf_bucket to 8-byte boundary
    ('tf_bucket', np.int64,  (MAX_TF,)),    # current bucket (ts // tf) per TF
])

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