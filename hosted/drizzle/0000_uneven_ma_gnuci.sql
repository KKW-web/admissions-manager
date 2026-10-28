CREATE TABLE `change_audit` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`at` text NOT NULL,
	`actor` text NOT NULL,
	`action` text NOT NULL,
	`target` text NOT NULL,
	`detail` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `mutation_guards` (
	`token` text PRIMARY KEY NOT NULL
);
--> statement-breakpoint
CREATE TABLE `teacher_members` (
	`user_id` text PRIMARY KEY NOT NULL,
	`email` text NOT NULL,
	`classroom` text NOT NULL,
	`active` integer DEFAULT 1 NOT NULL
);
--> statement-breakpoint
CREATE TABLE `site_owner` (
	`id` integer PRIMARY KEY NOT NULL,
	`user_id` text NOT NULL,
	`email` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `admission_records` (
	`kind` text NOT NULL,
	`id` integer NOT NULL,
	`student_id` integer,
	`application_id` integer,
	`identity` text,
	`payload` text NOT NULL,
	`version` integer DEFAULT 1 NOT NULL,
	PRIMARY KEY(`kind`, `id`)
);
--> statement-breakpoint
CREATE UNIQUE INDEX `admission_records_identity_unique` ON `admission_records` (`identity`);--> statement-breakpoint
CREATE TABLE `site_settings` (
	`key` text PRIMARY KEY NOT NULL,
	`value` text NOT NULL
);
