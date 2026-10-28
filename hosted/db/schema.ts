import { sqliteTable, text, integer, primaryKey } from 'drizzle-orm/sqlite-core';
export const records=sqliteTable('admission_records',{kind:text('kind').notNull(),id:integer('id').notNull(),studentId:integer('student_id'),applicationId:integer('application_id'),identity:text('identity').unique(),payload:text('payload').notNull(),version:integer('version').notNull().default(1)},t=>[primaryKey({columns:[t.kind,t.id]})]);
export const owner=sqliteTable('site_owner',{id:integer('id').primaryKey(),userId:text('user_id').notNull(),email:text('email').notNull()});
export const members=sqliteTable('teacher_members',{userId:text('user_id').primaryKey(),email:text('email').notNull().unique(),classroom:text('classroom').notNull(),active:integer('active').notNull().default(1),role:text('role').notNull().default('teacher'),academicYear:text('academic_year').notNull().default('2026')});
export const settings=sqliteTable('site_settings',{key:text('key').primaryKey(),value:text('value').notNull()});
export const audit=sqliteTable('change_audit',{id:integer('id').primaryKey({autoIncrement:true}),at:text('at').notNull(),actor:text('actor').notNull(),action:text('action').notNull(),target:text('target').notNull(),detail:text('detail').notNull()});
export const guards=sqliteTable('mutation_guards',{token:text('token').primaryKey()});
