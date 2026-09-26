import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { RolloutSlider } from '../components/RolloutSlider';

function renderSlider(props: Partial<React.ComponentProps<typeof RolloutSlider>> = {}) {
  const onCommit = vi.fn();
  const view = render(
    <RolloutSlider percentage={0} onCommit={onCommit} debounceMs={400} {...props} />,
  );
  const input = screen.getByLabelText('Percentage rollout') as HTMLInputElement;
  return { onCommit, input, view };
}

describe('RolloutSlider debouncing', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('commits once for a whole drag instead of once per step', () => {
    const { onCommit, input } = renderSlider();

    [10, 25, 40, 55, 70].forEach((value) => {
      fireEvent.change(input, { target: { value: String(value) } });
    });

    // Mid-drag nothing has been persisted yet.
    expect(onCommit).not.toHaveBeenCalled();
    expect(input.value).toBe('70');

    act(() => {
      vi.advanceTimersByTime(400);
    });

    expect(onCommit).toHaveBeenCalledTimes(1);
    expect(onCommit).toHaveBeenCalledWith(70);
  });

  it('keeps restarting the timer while the drag continues', () => {
    const { onCommit, input } = renderSlider();

    for (let step = 1; step <= 5; step += 1) {
      fireEvent.change(input, { target: { value: String(step * 10) } });
      act(() => {
        vi.advanceTimersByTime(300);
      });
    }

    expect(onCommit).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(400);
    });
    expect(onCommit).toHaveBeenCalledTimes(1);
    expect(onCommit).toHaveBeenCalledWith(50);
  });

  it('flushes on release so the last value is never left unsaved', () => {
    const { onCommit, input } = renderSlider();

    fireEvent.change(input, { target: { value: '35' } });
    fireEvent.pointerUp(input);

    expect(onCommit).toHaveBeenCalledTimes(1);
    expect(onCommit).toHaveBeenCalledWith(35);

    // The pending timer must not fire a second, duplicate mutation.
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(onCommit).toHaveBeenCalledTimes(1);
  });

  it('flushes on keyboard use and on blur', () => {
    const { onCommit, input } = renderSlider();

    fireEvent.change(input, { target: { value: '60' } });
    fireEvent.keyUp(input, { key: 'ArrowRight' });
    expect(onCommit).toHaveBeenCalledWith(60);

    fireEvent.change(input, { target: { value: '80' } });
    fireEvent.blur(input);
    expect(onCommit).toHaveBeenLastCalledWith(80);
    expect(onCommit).toHaveBeenCalledTimes(2);
  });

  it('does not commit a value the server already has', () => {
    const { onCommit, input } = renderSlider({ percentage: 50 });

    fireEvent.change(input, { target: { value: '50' } });
    act(() => {
      vi.advanceTimersByTime(400);
    });
    expect(onCommit).not.toHaveBeenCalled();
  });

  it('shows the dragged value immediately and marks it as saving', () => {
    const { input } = renderSlider();

    fireEvent.change(input, { target: { value: '42' } });

    expect(input.value).toBe('42');
    expect(input).toHaveAttribute('aria-valuetext', '42 percent, saving');
    expect(screen.getByText('saving')).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(400);
    });
    expect(input).toHaveAttribute('aria-valuetext', '42 percent');
  });

  it('does not yank the thumb back when a background poll returns stale state', () => {
    const onCommit = vi.fn();
    const { rerender } = render(
      <RolloutSlider percentage={0} onCommit={onCommit} debounceMs={400} />,
    );
    const input = screen.getByLabelText('Percentage rollout') as HTMLInputElement;

    fireEvent.change(input, { target: { value: '65' } });
    // A poll lands before the debounce fires, still reporting the old value.
    rerender(<RolloutSlider percentage={0} onCommit={onCommit} debounceMs={400} />);
    expect(input.value).toBe('65');

    act(() => {
      vi.advanceTimersByTime(400);
    });
    expect(onCommit).toHaveBeenCalledWith(65);
  });

  it('adopts the server value once the user is not editing', () => {
    const onCommit = vi.fn();
    const { rerender } = render(
      <RolloutSlider percentage={0} onCommit={onCommit} debounceMs={400} />,
    );
    const input = screen.getByLabelText('Percentage rollout') as HTMLInputElement;

    rerender(<RolloutSlider percentage={90} onCommit={onCommit} debounceMs={400} />);
    expect(input.value).toBe('90');
    expect(onCommit).not.toHaveBeenCalled();
  });

  it('does not commit after unmount', () => {
    const { onCommit, input, view } = renderSlider();

    fireEvent.change(input, { target: { value: '30' } });
    view.unmount();

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(onCommit).not.toHaveBeenCalled();
  });

  it('still commits a pending edit when the control becomes disabled mid-drag', () => {
    const onCommit = vi.fn();
    const { rerender } = render(
      <RolloutSlider percentage={0} onCommit={onCommit} debounceMs={400} />,
    );
    const input = screen.getByLabelText('Percentage rollout') as HTMLInputElement;

    fireEvent.change(input, { target: { value: '45' } });
    // The kill switch flips and disables the slider before the timer fires.
    rerender(<RolloutSlider percentage={0} onCommit={onCommit} debounceMs={400} disabled />);

    act(() => {
      vi.advanceTimersByTime(400);
    });
    expect(onCommit).toHaveBeenCalledWith(45);
  });

  it('a full drag across the range still produces a single mutation', () => {
    const { onCommit, input } = renderSlider();

    for (let value = 0; value <= 100; value += 5) {
      fireEvent.change(input, { target: { value: String(value) } });
    }
    fireEvent.pointerUp(input);

    expect(onCommit).toHaveBeenCalledTimes(1);
    expect(onCommit).toHaveBeenCalledWith(100);
  });
});

describe('RolloutSlider accessibility', () => {
  it('exposes the value to assistive technology', () => {
    const { input } = renderSlider({ percentage: 25 });
    expect(input).toHaveAttribute('aria-valuetext', '25 percent');
    expect(screen.getByText('25%')).toBeInTheDocument();
  });

  it('is disabled while the kill switch is off', () => {
    const { input } = renderSlider({ disabled: true });
    expect(input).toBeDisabled();
  });

});
