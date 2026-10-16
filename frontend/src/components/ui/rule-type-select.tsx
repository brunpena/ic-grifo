"use client";

import { Check, ChevronDown } from "lucide-react";
import { type KeyboardEvent, useEffect, useId, useRef, useState } from "react";
import { RULE_TYPES, type RuleType } from "@/lib/design/tokens";
import { useFloatingPosition } from "@/lib/floating";
import { cn } from "@/lib/utils";
import { RuleTypeDot } from "./badge";
import { FIELD_CLASSES } from "./input";

const TYPES = Object.keys(RULE_TYPES) as RuleType[];

type RuleTypeSelectProps<AllowAll extends boolean> = {
  value: AllowAll extends true ? RuleType | null : RuleType;
  onChange: (value: AllowAll extends true ? RuleType | null : RuleType) => void;
  /** Inclui uma opção sem tipo (`null`), para filtros. */
  allowAll?: AllowAll;
  allLabel?: string;
  "aria-label"?: string;
  "aria-labelledby"?: string;
  id?: string;
  autoFocus?: boolean;
  disabled?: boolean;
  className?: string;
};

/**
 * Select de tipo de regra com a bolinha de cor em cada opção, o que o <select>
 * nativo não permite. Segue o padrão ARIA de listbox de seleção única.
 *
 * A lista não usa portal: fica no mesmo ramo do DOM para que um Popover em volta
 * não a trate como "clique fora".
 */
export function RuleTypeSelect<AllowAll extends boolean = false>({
  value,
  onChange,
  allowAll,
  allLabel = "Todos os tipos",
  id,
  autoFocus,
  disabled,
  className,
  ...aria
}: RuleTypeSelectProps<AllowAll>) {
  const options: (RuleType | null)[] = allowAll ? [null, ...TYPES] : TYPES;
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [width, setWidth] = useState<number>();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const listId = useId();
  const optionId = (i: number) => `${listId}-${i}`;

  useFloatingPosition(open, triggerRef, listRef, { placement: "bottom", align: "start", offset: 4 });

  useEffect(() => {
    if (!open) return;
    listRef.current?.focus();
    const onPointerDown = (e: PointerEvent) => {
      const target = e.target as Node;
      if (!listRef.current?.contains(target) && !triggerRef.current?.contains(target)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  useEffect(() => {
    if (open) document.getElementById(optionId(active))?.scrollIntoView({ block: "nearest" });
  });

  const labelOf = (option: RuleType | null) => (option ? RULE_TYPES[option].label : allLabel);

  const openList = () => {
    setActive(Math.max(0, options.indexOf(value)));
    setWidth(triggerRef.current?.offsetWidth);
    setOpen(true);
  };

  const close = () => {
    setOpen(false);
    triggerRef.current?.focus();
  };

  const select = (option: RuleType | null) => {
    onChange(option as RuleTypeSelectProps<AllowAll>["value"]);
    close();
  };

  const onTriggerKeyDown = (e: KeyboardEvent) => {
    if (["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) {
      e.preventDefault();
      openList();
    }
  };

  const onListKeyDown = (e: KeyboardEvent) => {
    const last = options.length - 1;
    const moves: Record<string, number> = {
      ArrowDown: Math.min(active + 1, last),
      ArrowUp: Math.max(active - 1, 0),
      Home: 0,
      End: last,
    };
    if (e.key in moves) {
      e.preventDefault();
      setActive(moves[e.key]);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      select(options[active]);
    } else if (e.key === "Escape") {
      // Não deixa o Esc fechar também o Popover ou Dialog em volta.
      e.preventDefault();
      e.stopPropagation();
      close();
    } else if (e.key === "Tab") {
      setOpen(false);
    }
  };

  return (
    <div className={cn("relative", className)}>
      <button
        ref={triggerRef}
        type="button"
        id={id}
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        autoFocus={autoFocus}
        disabled={disabled}
        onClick={() => (open ? setOpen(false) : openList())}
        onKeyDown={onTriggerKeyDown}
        className={cn(FIELD_CLASSES, "flex h-9 cursor-pointer items-center gap-2 pr-8 text-left")}
        {...aria}
      >
        {value && <RuleTypeDot type={value} />}
        <span className="truncate">{labelOf(value)}</span>
        <ChevronDown
          size={16}
          strokeWidth={1.75}
          aria-hidden
          className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-foreground-subtle"
        />
      </button>

      {open && (
        <ul
          ref={listRef}
          id={listId}
          role="listbox"
          tabIndex={-1}
          aria-label={aria["aria-label"]}
          aria-labelledby={aria["aria-labelledby"]}
          aria-activedescendant={optionId(active)}
          onKeyDown={onListKeyDown}
          style={{ minWidth: width }}
          className="fixed top-0 left-0 z-50 max-h-64 overflow-auto rounded-lg border border-border bg-surface p-1 shadow-md outline-none animate-enter"
        >
          {options.map((option, i) => (
            <li
              key={option ?? "all"}
              id={optionId(i)}
              role="option"
              aria-selected={option === value}
              onPointerMove={() => setActive(i)}
              onClick={() => select(option)}
              className={cn(
                "flex h-8 cursor-pointer items-center gap-2 rounded-sm px-2 text-sm",
                i === active && "bg-surface-hover",
              )}
            >
              {option ? <RuleTypeDot type={option} /> : <span aria-hidden className="size-2" />}
              <span className="flex-1">{labelOf(option)}</span>
              {option === value && (
                <Check size={16} strokeWidth={1.75} aria-hidden className="text-accent" />
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
